"""A scriptable stand-in for DiscordClient, for scanner and engine tests."""

from __future__ import annotations

from wipecord.client import ApiResult, Redactor
from wipecord.ratelimit import RateLimiter

from conftest import FakeSleeper


def message(
    message_id: str,
    author_id: str = "ME",
    content: str = "hello",
    *,
    pinned: bool = False,
    hit: bool = True,
    timestamp: str = "2024-01-01T00:00:00+00:00",
) -> dict:
    return {
        "id": str(message_id),
        "author": {"id": author_id, "username": f"user{author_id}"},
        "content": content,
        "pinned": pinned,
        "hit": hit,
        "timestamp": timestamp,
        "type": 0,
        "attachments": [],
    }


def search_page(messages: list[dict], total: int | None = None) -> ApiResult:
    """One search response. Discord wraps each hit in a context group."""
    return ApiResult(
        status=200,
        data={
            "total_results": total if total is not None else len(messages),
            "messages": [[m] for m in messages],
        },
        headers={},
    )


class FakeClient:
    """Replays scripted search/history pages and records deletions."""

    def __init__(
        self,
        *,
        channel: dict | None = None,
        user: dict | None = None,
        search_pages: list | None = None,
        history_pages: list | None = None,
        delete_results: dict | None = None,
        on_delete=None,
    ) -> None:
        self.limiter = RateLimiter(sleeper=FakeSleeper())
        self.redact = Redactor()
        self._channel = channel or {"id": "C1", "type": 0, "name": "general", "guild_id": "G1"}
        self._user = user or {"id": "ME", "username": "me"}
        self._search_pages = list(search_pages or [])
        self._history_pages = list(history_pages or [])
        self._delete_results = delete_results or {}
        self.on_delete = on_delete
        self.search_calls: list[dict] = []
        self.history_calls: list[dict] = []
        self.deleted: list[str] = []
        self.closed = False

    def verify_token(self) -> dict:
        return self._user

    def get_channel(self, channel_id: str) -> dict:
        if isinstance(self._channel, Exception):
            raise self._channel
        return self._channel

    def search(self, **kwargs) -> ApiResult:
        self.search_calls.append(kwargs)
        if not self._search_pages:
            return search_page([], total=0)
        page = self._search_pages.pop(0)
        if isinstance(page, Exception):
            raise page
        return page

    def list_messages(self, channel_id: str, **kwargs) -> list[dict]:
        self.history_calls.append({"channel_id": channel_id, **kwargs})
        if not self._history_pages:
            return []
        page = self._history_pages.pop(0)
        if isinstance(page, Exception):
            raise page
        return page

    def delete_message(self, channel_id: str, message_id: str) -> int:
        if self.on_delete is not None:
            self.on_delete(message_id)
        result = self._delete_results.get(message_id, 204)
        if isinstance(result, Exception):
            self.deleted.append(message_id)
            raise result
        self.deleted.append(message_id)
        return result

    def close(self) -> None:
        self.closed = True
