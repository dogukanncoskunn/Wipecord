"""Pacing and rate-limit compliance.

Four layers, in the order they engage:

1. A randomised human-scale delay between mutating requests.
2. Proactive bucket tracking - when the headers say a bucket is exhausted we
   wait for it to reset *before* sending, instead of sending and getting a 429.
3. Reactive 429 handling - honour `retry_after`, add jitter, retry the same
   item, slow the baseline down if it keeps happening, and abort outright
   rather than hammer.
4. Transport backoff for 5xx and network errors.

Sleeping goes through `Sleeper`, which waits on a stop `threading.Event` rather
than calling `time.sleep`. That is what makes the Stop button take effect
instantly even in the middle of a 30-second breather.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

from . import config


class Stopped(Exception):
    """Raised when the user asked to stop while we were waiting."""


class RateLimitAbort(Exception):
    """Too many consecutive 429s - refuse to keep pushing."""


class SleeperProtocol(Protocol):
    def sleep(self, seconds: float) -> bool:
        """Sleep for `seconds`. Return False if a stop was requested."""


class Sleeper:
    """Interruptible sleep backed by a stop event."""

    def __init__(self, stop_event: threading.Event | None = None) -> None:
        self.stop_event = stop_event or threading.Event()

    def sleep(self, seconds: float) -> bool:
        if self.stop_event.is_set():
            return False
        if seconds <= 0:
            return True
        # Event.wait returns True when the event was set during the wait, so a
        # stop cuts the sleep short instead of running it to completion.
        return not self.stop_event.wait(seconds)


@dataclass
class Bucket:
    """Last known state of one rate-limit bucket."""

    remaining: int | None = None
    reset_after: float = 0.0
    observed_at: float = field(default_factory=time.monotonic)

    def wait_needed(self, now: float | None = None) -> float:
        if self.remaining is None or self.remaining > 0:
            return 0.0
        elapsed = (now if now is not None else time.monotonic()) - self.observed_at
        return max(0.0, self.reset_after - elapsed)


# notify(kind, seconds, detail) - kind is one of "bucket", "ratelimit",
# "global", "transport". Lets the engine log a wait without the limiter
# knowing anything about the UI.
NotifyFn = Callable[[str, float, str], None]


class RateLimiter:
    def __init__(
        self,
        delay_min: float = config.DEFAULT_DELAY_MIN,
        delay_max: float = config.DEFAULT_DELAY_MAX,
        *,
        sleeper: SleeperProtocol | None = None,
        rng: random.Random | None = None,
        notify: NotifyFn | None = None,
    ) -> None:
        self.delay_min = max(config.DELAY_FLOOR, float(delay_min))
        self.delay_max = max(self.delay_min, float(delay_max))
        self._sleeper = sleeper or Sleeper()
        self._rng = rng or random.Random()
        self._notify = notify or (lambda kind, seconds, detail: None)
        self._buckets: dict[str, Bucket] = {}
        self._consecutive_429 = 0
        self._multiplier = 1.0

    # --- introspection, used by the UI and by tests --------------------------

    @property
    def multiplier(self) -> float:
        return self._multiplier

    @property
    def consecutive_429(self) -> int:
        return self._consecutive_429

    @property
    def effective_range(self) -> tuple[float, float]:
        return self.delay_min * self._multiplier, self.delay_max * self._multiplier

    # --- sleeping ------------------------------------------------------------

    def sleep(self, seconds: float) -> None:
        if not self._sleeper.sleep(seconds):
            raise Stopped

    def next_delay(self) -> float:
        """The human-scale delay to apply before the next deletion.

        Returned rather than slept so the caller can log it first - the UI shows
        "waiting 2.3s" while the wait is happening, not after.
        """
        low, high = self.effective_range
        return self._rng.uniform(low, high)

    def breather(self) -> float:
        """A longer pause, taken every `BREATHER_EVERY` deletions."""
        seconds = self._rng.uniform(config.BREATHER_MIN, config.BREATHER_MAX)
        self._notify("breather", seconds, "")
        self.sleep(seconds)
        return seconds

    def _jitter(self) -> float:
        return self._rng.uniform(config.RATE_LIMIT_JITTER_MIN, config.RATE_LIMIT_JITTER_MAX)

    # --- bucket tracking -----------------------------------------------------

    def before_request(self, key: str) -> None:
        """Wait out an exhausted bucket before sending anything."""
        bucket = self._buckets.get(key)
        if bucket is None:
            return
        wait = bucket.wait_needed()
        if wait > 0:
            total = wait + self._jitter()
            self._notify("bucket", total, key)
            self.sleep(total)
            bucket.remaining = None

    def observe(self, key: str, status: int, headers) -> None:
        """Record bucket state from a response, and reset the 429 streak."""
        remaining = _to_int(headers.get("X-RateLimit-Remaining"))
        reset_after = _to_float(headers.get("X-RateLimit-Reset-After"))
        if remaining is not None or reset_after is not None:
            self._buckets[key] = Bucket(
                remaining=remaining,
                reset_after=reset_after or 0.0,
                observed_at=time.monotonic(),
            )
        if status != 429 and status < 500:
            self._consecutive_429 = 0

    # --- 429 handling --------------------------------------------------------

    def handle_429(self, key: str, retry_after: float, *, is_global: bool = False) -> float:
        """Honour a 429. Returns the seconds waited.

        Raises RateLimitAbort once the streak hits the configured maximum: at
        that point something is wrong with our assumptions and continuing risks
        a Cloudflare IP ban, which is far worse than a failed job.
        """
        self._consecutive_429 += 1
        if self._consecutive_429 >= config.MAX_CONSECUTIVE_429:
            raise RateLimitAbort(
                f"{self._consecutive_429} consecutive rate limits; stopping to protect the account"
            )
        if self._consecutive_429 >= config.ADAPTIVE_429_THRESHOLD:
            self._multiplier = min(
                config.ADAPTIVE_MAX_MULTIPLIER, self._multiplier * config.ADAPTIVE_FACTOR
            )

        wait = max(0.0, float(retry_after)) + self._jitter()
        if is_global:
            wait += config.GLOBAL_429_EXTRA
        # The bucket is spent regardless of what the headers claimed.
        self._buckets.pop(key, None)
        self._notify("global" if is_global else "ratelimit", wait, key)
        self.sleep(wait)
        return wait

    def transport_backoff(self, attempt: int, detail: str = "") -> float:
        """Exponential backoff for 5xx and network failures."""
        wait = config.TRANSPORT_BACKOFF_BASE * (2 ** max(0, attempt - 1)) + self._jitter()
        self._notify("transport", wait, detail)
        self.sleep(wait)
        return wait


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
