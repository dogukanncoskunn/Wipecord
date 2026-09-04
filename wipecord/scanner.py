"""Finding the messages a run would delete.

Two strategies, in order:

1. The search API, which accepts `author_id` and therefore filters server-side.
   Other people's messages are never even transferred, and `total_results`
   gives us a real total for the progress bar and ETA.
2. Plain history pagination, used when search is unavailable. Slower, and it
   has to filter client-side, but it always works.

Whichever path runs, the same hard rule applies: a message whose author is not
the token owner can never reach the output. That is checked again on every
message, not just requested from the server.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Callable, Iterator

from . import config
from .client import DiscordClient, DiscordError
from .snowflake import date_range_to_snowflakes

# Discord channel type ids that are direct messages rather than guild channels.
DM_CHANNEL_TYPES = {1, 3}


class Mode(str, Enum):
    ALL = "all"
    LAST_N = "last_n"
    DATE_RANGE = "date_range"


@dataclass(frozen=True)
class ScanCriteria:
    mode: Mode = Mode.ALL
    limit: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    skip_pinned: bool = True

    def bounds(self) -> tuple[int | None, int | None]:
        """The (min_id, max_id) snowflake window this criteria implies."""
        if self.mode is Mode.DATE_RANGE:
            return date_range_to_snowflakes(self.start_date, self.end_date)
        return None, None


@dataclass(frozen=True)
class ChannelInfo:
    id: str
    name: str
    is_dm: bool
    guild_id: str | None = None

    @property
    def label(self) -> str:
        return self.name if self.is_dm else f"#{self.name}"


@dataclass(frozen=True)
class MessageRef:
    id: str
    timestamp: str
    summary: str
    pinned: bool = False
    attachments: int = 0
    type: int = 0


def summarise(message: dict, width: int = 60) -> str:
    """A single-line preview of a message, for the log window."""
    content = (message.get("content") or "").replace("\n", " ").strip()
    if not content:
        parts = []
        if message.get("attachments"):
            parts.append(f"[{len(message['attachments'])} attachment(s)]")
        if message.get("embeds"):
            parts.append("[embed]")
        if message.get("sticker_items"):
            parts.append("[sticker]")
        content = " ".join(parts) or "[no text]"
    return content if len(content) <= width else content[: width - 1] + "…"


def to_ref(message: dict) -> MessageRef:
    return MessageRef(
        id=str(message.get("id")),
        timestamp=str(message.get("timestamp") or ""),
        summary=summarise(message),
        pinned=bool(message.get("pinned")),
        attachments=len(message.get("attachments") or ()),
        type=int(message.get("type") or 0),
    )


LogFn = Callable[[str, str], None]  # (level, text)


class Scanner:
    def __init__(
        self,
        client: DiscordClient,
        author_id: str,
        *,
        log: LogFn | None = None,
    ) -> None:
        self._client = client
        self._author_id = str(author_id)
        self._log = log or (lambda level, text: None)
        self.total_hint: int | None = None
        self.used_fallback = False

    # --- channel -------------------------------------------------------------

    def describe_channel(self, channel_id: str) -> ChannelInfo:
        """Resolve a channel id to something a human can recognise.

        Showing the name back to the user before anything is deleted is the
        single most effective guard against wiping the wrong conversation.
        """
        data = self._client.get_channel(channel_id)
        channel_type = int(data.get("type") or 0)
        is_dm = channel_type in DM_CHANNEL_TYPES
        if is_dm:
            recipients = data.get("recipients") or []
            names = [r.get("global_name") or r.get("username") or "?" for r in recipients]
            name = data.get("name") or ", ".join(names) or "Direct Message"
        else:
            name = data.get("name") or channel_id
        return ChannelInfo(
            id=str(data.get("id") or channel_id),
            name=name,
            is_dm=is_dm,
            guild_id=str(data["guild_id"]) if data.get("guild_id") else None,
        )

    # --- the absolute rule ---------------------------------------------------

    def _is_mine(self, message: dict) -> bool:
        author = message.get("author") or {}
        return str(author.get("id")) == self._author_id

    def _accepts(self, message: dict, criteria: ScanCriteria) -> bool:
        if not self._is_mine(message):
            return False
        if criteria.skip_pinned and message.get("pinned"):
            return False
        return True

    # --- scanning ------------------------------------------------------------

    def scan(self, channel: ChannelInfo, criteria: ScanCriteria) -> Iterator[MessageRef]:
        """Yield the messages a run would delete, newest first.

        A generator, so the caller can stop early (LAST_N) or on user request
        without waiting for a full crawl.
        """
        self.total_hint = None
        self.used_fallback = False
        try:
            yield from self._scan_via_search(channel, criteria)
            return
        except DiscordError as exc:
            self._log(
                "warn",
                f"Search unavailable ({exc.message}); falling back to history pagination.",
            )
        self.used_fallback = True
        self.total_hint = None
        yield from self._scan_via_history(channel, criteria)

    def _scan_via_search(
        self, channel: ChannelInfo, criteria: ScanCriteria
    ) -> Iterator[MessageRef]:
        min_id, max_id = criteria.bounds()
        offset = 0
        yielded = 0
        seen: set[str] = set()

        while True:
            result = self._client.search(
                channel_id=channel.id,
                author_id=self._author_id,
                guild_id=channel.guild_id,
                offset=offset,
                min_id=min_id,
                max_id=max_id,
            )

            # 202 means the search index is still warming up. Not an error - it
            # resolves on its own, so wait it out rather than falling back.
            if result.status == 202:
                retry = float((result.data or {}).get("retry_after") or 2.0)
                self._log("wait", f"Discord is building the search index; retrying in {retry:.0f}s.")
                self._client.limiter.sleep(retry)
                continue

            data = result.data if isinstance(result.data, dict) else {}
            if self.total_hint is None:
                total = data.get("total_results")
                if isinstance(total, int):
                    self.total_hint = total

            groups = data.get("messages") or []
            if not groups:
                return

            page_ids: list[int] = []
            for group in groups:
                # Search returns each hit with its surrounding context; the hit
                # itself is flagged. Fall back to the whole group if the flag is
                # absent, since the author check below is what actually decides.
                hits = [m for m in group if m.get("hit")] or group
                for message in hits:
                    message_id = str(message.get("id"))
                    numeric_id = _as_int(message_id)
                    # Recorded before the duplicate check: the window slide needs
                    # the oldest id on the page even when the page overlaps one
                    # we have already consumed.
                    if numeric_id is not None:
                        page_ids.append(numeric_id)
                    if message_id in seen:
                        continue
                    seen.add(message_id)
                    if numeric_id is None:
                        continue
                    # Context messages can fall outside the requested window.
                    if min_id is not None and numeric_id < min_id:
                        continue
                    if max_id is not None and numeric_id > max_id:
                        continue
                    if not self._accepts(message, criteria):
                        continue
                    yield to_ref(message)
                    yielded += 1
                    if criteria.limit is not None and yielded >= criteria.limit:
                        return

            offset += config.SEARCH_PAGE_SIZE
            if self.total_hint is not None and offset >= self.total_hint:
                return
            if offset >= config.SEARCH_MAX_OFFSET:
                # Discord refuses deeper offsets, so slide the window down to
                # just below the oldest id on this page and start paging again.
                if not page_ids:
                    return
                max_id = min(page_ids) - 1
                offset = 0
                self._log("info", "Reached the search depth limit; continuing from an older window.")

    def _scan_via_history(
        self, channel: ChannelInfo, criteria: ScanCriteria
    ) -> Iterator[MessageRef]:
        min_id, max_id = criteria.bounds()
        before = max_id
        yielded = 0

        while True:
            batch = self._client.list_messages(
                channel.id, before=before, limit=config.MESSAGES_PAGE_SIZE
            )
            if not batch:
                return

            for message in batch:
                numeric_id = _as_int(message.get("id"))
                if numeric_id is None:
                    continue
                # History runs newest-first, so once we pass the lower bound
                # every remaining message is older than the range.
                if min_id is not None and numeric_id < min_id:
                    return
                if not self._accepts(message, criteria):
                    continue
                yield to_ref(message)
                yielded += 1
                if criteria.limit is not None and yielded >= criteria.limit:
                    return

            before = batch[-1].get("id")
            if before is None:
                return


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
