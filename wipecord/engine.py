"""The deletion worker.

Runs on one background thread and communicates with the UI exclusively through
an event queue. It never imports or touches tkinter, which is what lets the
whole pipeline be tested headlessly.

Pause and stop are both `threading.Event`s. Stop doubles as the interrupt for
every sleep in the rate limiter, so pressing Stop halfway through a 30-second
breather takes effect immediately instead of at the end of the pause.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field

from . import config
from .client import AuthError, DiscordClient, DiscordError, Redactor, TransportError
from .events import (
    DoneEvent,
    Level,
    LogEvent,
    PreviewEvent,
    ProgressEvent,
    State,
    StateEvent,
    Summary,
)
from .ratelimit import RateLimitAbort, RateLimiter, Sleeper, Stopped
from .scanner import ChannelInfo, MessageRef, ScanCriteria, Scanner


@dataclass
class Job:
    token: str
    channel_id: str
    criteria: ScanCriteria = field(default_factory=ScanCriteria)
    delay_min: float = config.DEFAULT_DELAY_MIN
    delay_max: float = config.DEFAULT_DELAY_MAX
    dry_run: bool = True


class DeletionEngine:
    def __init__(self, events: queue.Queue | None = None) -> None:
        self.events: queue.Queue = events or queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        # Set means "running"; cleared means "paused".
        self._running = threading.Event()
        self._running.set()
        # Seams for tests: the defaults build a real client and a real,
        # actually-sleeping limiter.
        self._client_factory = _default_client_factory
        self._limiter_factory = _default_limiter_factory

    # --- control -------------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def paused(self) -> bool:
        return not self._running.is_set()

    def start(self, job: Job) -> None:
        if self.busy:
            raise RuntimeError("a job is already running")
        self._stop.clear()
        self._running.set()
        self._thread = threading.Thread(target=self._run, args=(job,), daemon=True)
        self._thread.start()

    def pause(self) -> None:
        if self.busy and not self.paused:
            self._running.clear()
            self._emit(StateEvent(State.PAUSED))
            self._log(Level.WARN, "Paused.")

    def resume(self) -> None:
        if self.paused:
            self._running.set()
            self._log(Level.INFO, "Resumed.")

    def stop(self) -> None:
        self._stop.set()
        # A paused worker is parked on _running; release it so it can observe
        # the stop flag and unwind instead of hanging.
        self._running.set()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    # --- event plumbing ------------------------------------------------------

    def _emit(self, event) -> None:
        self.events.put(event)

    def _log(self, level: Level, text: str) -> None:
        self._emit(LogEvent(level, text))

    def _checkpoint(self) -> None:
        """Honour pause, and raise if the user asked to stop."""
        while not self._running.wait(0.2):
            if self._stop.is_set():
                raise Stopped
        if self._stop.is_set():
            raise Stopped

    # --- the job -------------------------------------------------------------

    def _run(self, job: Job) -> None:
        started = time.monotonic()
        summary = Summary(dry_run=job.dry_run)
        redactor = Redactor()
        redactor.add(job.token)
        client = None

        def notify(kind: str, seconds: float, detail: str) -> None:
            messages = {
                "bucket": f"Rate-limit bucket is empty; waiting {seconds:.1f}s.",
                "ratelimit": f"Rate limited by Discord; waiting {seconds:.1f}s.",
                "global": f"GLOBAL rate limit hit; backing off {seconds:.1f}s.",
                "breather": f"Taking a {seconds:.0f}s breather to keep the pace natural.",
                "transport": f"Connection problem; retrying in {seconds:.1f}s.",
            }
            level = Level.ERROR if kind == "global" else Level.WAIT
            self._log(level, redactor(messages.get(kind, f"Waiting {seconds:.1f}s.")))

        try:
            limiter = self._limiter_factory(job, self._stop, notify)
            client = self._client_factory(job.token, limiter, redactor)

            me = client.verify_token()
            author_id = str(me.get("id"))
            username = me.get("global_name") or me.get("username") or author_id
            self._log(Level.SUCCESS, f"Signed in as {username} ({author_id}).")

            scanner = Scanner(
                client, author_id, log=lambda lvl, text: self._log(Level(lvl), redactor(text))
            )
            channel = scanner.describe_channel(job.channel_id)
            kind = "DM" if channel.is_dm else "server channel"
            self._log(Level.INFO, f"Target: {channel.label} ({kind}).")

            found = self._scan(scanner, channel, job)
            summary = Summary(
                scanned=len(found), dry_run=job.dry_run, stopped=self._stop.is_set()
            )
            self._emit(PreviewEvent(messages=tuple(found), channel_label=channel.label))

            if job.dry_run:
                self._log(
                    Level.SUCCESS,
                    f"Preview complete: {len(found)} message(s) would be deleted. "
                    "Nothing was changed.",
                )
            else:
                summary = self._delete(client, limiter, channel, found, summary)

        except Stopped:
            summary = Summary(**{**_as_dict(summary), "stopped": True})
            self._log(Level.WARN, "Stopped by user.")
        except RateLimitAbort as exc:
            summary = Summary(**{**_as_dict(summary), "error": str(exc)})
            self._log(
                Level.ERROR,
                f"{exc} Wait a few minutes before trying again.",
            )
        except AuthError as exc:
            summary = Summary(**{**_as_dict(summary), "error": exc.message})
            self._log(Level.ERROR, f"Authentication failed: {redactor(exc.message)}")
        except (DiscordError, TransportError) as exc:
            summary = Summary(**{**_as_dict(summary), "error": str(exc)})
            self._log(Level.ERROR, redactor(exc))
        except Exception as exc:  # unexpected - still must not kill the UI
            summary = Summary(**{**_as_dict(summary), "error": str(exc)})
            self._log(Level.ERROR, f"Unexpected error: {redactor(exc)}")
        finally:
            if client is not None:
                client.close()
            summary = Summary(
                **{**_as_dict(summary), "duration": time.monotonic() - started}
            )
            self._emit(StateEvent(State.DONE))
            self._emit(DoneEvent(summary))

    def _scan(self, scanner: Scanner, channel: ChannelInfo, job: Job) -> list[MessageRef]:
        self._emit(StateEvent(State.SCANNING))
        self._log(Level.INFO, "Searching for your messages…")
        found: list[MessageRef] = []
        for ref in scanner.scan(channel, job.criteria):
            self._checkpoint()
            found.append(ref)
            if len(found) % 25 == 0:
                self._emit(ProgressEvent(done=len(found), total=scanner.total_hint or 0))
                self._log(Level.INFO, f"Found {len(found)} so far…")
        self._emit(ProgressEvent(done=len(found), total=len(found)))
        return found

    def _delete(
        self,
        client: DiscordClient,
        limiter: RateLimiter,
        channel: ChannelInfo,
        found: list[MessageRef],
        summary: Summary,
    ) -> Summary:
        self._emit(StateEvent(State.DELETING))
        total = len(found)
        deleted = skipped = failed = 0
        started = time.monotonic()

        for index, ref in enumerate(found, start=1):
            self._checkpoint()
            try:
                status = client.delete_message(channel.id, ref.id)
                if status == 404:
                    skipped += 1
                    self._log(Level.WARN, f"Already gone: {ref.summary}")
                else:
                    deleted += 1
                    self._log(Level.DELETE, f"Deleted: {ref.summary}")
            except AuthError as exc:
                # Losing access to one message should not abandon the rest.
                failed += 1
                self._log(Level.ERROR, f"Not allowed: {ref.summary} ({exc.message})")
            except DiscordError as exc:
                failed += 1
                self._log(Level.ERROR, f"Failed: {ref.summary} ({exc.message})")

            elapsed = time.monotonic() - started
            done = deleted + skipped + failed
            remaining = total - done
            average = elapsed / done if done else 0.0
            self._emit(
                ProgressEvent(
                    done=done,
                    total=total,
                    elapsed=elapsed,
                    eta=average * remaining if remaining else 0.0,
                )
            )

            if index >= total:
                break

            if index % config.BREATHER_EVERY == 0:
                limiter.breather()
                continue

            delay = limiter.next_delay()
            self._log(Level.WAIT, f"Waiting {delay:.1f}s…")
            limiter.sleep(delay)

        return Summary(
            scanned=summary.scanned,
            deleted=deleted,
            skipped=skipped,
            failed=failed,
            dry_run=False,
            stopped=self._stop.is_set(),
        )


def _as_dict(summary: Summary) -> dict:
    return {
        "scanned": summary.scanned,
        "deleted": summary.deleted,
        "skipped": summary.skipped,
        "failed": summary.failed,
        "duration": summary.duration,
        "dry_run": summary.dry_run,
        "stopped": summary.stopped,
        "error": summary.error,
    }


def _default_client_factory(token: str, limiter: RateLimiter, redactor: Redactor) -> DiscordClient:
    return DiscordClient(token, limiter, redactor=redactor)


def _default_limiter_factory(job: Job, stop: threading.Event, notify) -> RateLimiter:
    return RateLimiter(
        job.delay_min, job.delay_max, sleeper=Sleeper(stop), notify=notify
    )
