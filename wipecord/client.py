"""Thin, rate-limit-aware HTTP client for the Discord API.

Scope note: this talks to discord.com and nothing else. There is no telemetry,
no analytics, no proxy support and no attempt to look like the official client.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import requests

from . import config
from .ratelimit import RateLimiter


class Redactor:
    """Replaces registered secrets anywhere they appear in text.

    Every string that reaches a log window, a log file or an exception message
    goes through this. The requests library occasionally embeds headers or URLs
    in exception text, so redaction has to happen at the boundary rather than at
    the call sites we remember to guard.
    """

    PLACEHOLDER = "***REDACTED***"

    def __init__(self) -> None:
        self._secrets: set[str] = set()

    def add(self, secret: str | None) -> None:
        # Short strings would redact half the log; a Discord token is ~70 chars.
        if secret and len(secret) >= 8:
            self._secrets.add(secret)

    def __call__(self, text: Any) -> str:
        result = str(text)
        for secret in self._secrets:
            result = result.replace(secret, self.PLACEHOLDER)
        return result


class DiscordError(Exception):
    def __init__(self, status: int, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class AuthError(DiscordError):
    """401/403 - token invalid, expired, or lacking access."""


class TransportError(Exception):
    """Network failed repeatedly."""


@dataclass
class ApiResult:
    status: int
    data: Any
    headers: Mapping[str, str]


class DiscordClient:
    def __init__(
        self,
        token: str,
        limiter: RateLimiter,
        *,
        session: Any | None = None,
        redactor: Redactor | None = None,
    ) -> None:
        self._token = token
        self.limiter = limiter
        self.redact = redactor or Redactor()
        self.redact.add(token)
        self._session = session if session is not None else requests.Session()
        self._session.headers.update(
            {
                "Authorization": token,
                "User-Agent": config.USER_AGENT,
                "Accept": "application/json",
            }
        )

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:  # pragma: no cover - best effort
            pass

    # --- transport -----------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        bucket: str | None = None,
    ) -> ApiResult:
        """Perform one API call, absorbing rate limits and transient failures.

        The bucket argument groups requests that share a Discord rate-limit
        bucket. Deletes are bucketed per channel, which is how Discord limits
        them.
        """
        key = bucket or f"{method}:{path}"
        url = f"{config.API_BASE}{path}"
        attempt = 0

        while True:
            self.limiter.before_request(key)
            try:
                response = self._session.request(
                    method, url, params=params, timeout=config.REQUEST_TIMEOUT
                )
            except requests.RequestException as exc:
                attempt += 1
                if attempt > config.MAX_TRANSPORT_RETRIES:
                    raise TransportError(self.redact(exc)) from None
                self.limiter.transport_backoff(attempt, self.redact(exc))
                continue

            status = response.status_code
            self.limiter.observe(key, status, response.headers)
            body = _safe_json(response)

            if status == 429:
                retry_after = _retry_after(body, response.headers)
                self.limiter.handle_429(
                    key, retry_after, is_global=bool(_get(body, "global"))
                )
                continue

            if status >= 500:
                attempt += 1
                if attempt > config.MAX_TRANSPORT_RETRIES:
                    raise DiscordError(status, f"Discord returned {status} repeatedly")
                self.limiter.transport_backoff(attempt, f"HTTP {status}")
                continue

            if status in (401, 403):
                raise AuthError(status, _error_message(body, status), _get(body, "code"))

            if status >= 400 and status != 404:
                raise DiscordError(status, _error_message(body, status), _get(body, "code"))

            return ApiResult(status=status, data=body, headers=response.headers)

    # --- endpoints -----------------------------------------------------------

    def verify_token(self) -> dict:
        """GET /users/@me - validates the token and tells us who we are.

        The returned id is what every later filter compares against, so this
        call is mandatory before any deletion.
        """
        result = self.request("GET", "/users/@me", bucket="users:@me")
        if result.status == 404 or not isinstance(result.data, dict):
            raise AuthError(result.status, "Could not read the account for this token")
        return result.data

    def get_channel(self, channel_id: str) -> dict:
        result = self.request("GET", f"/channels/{channel_id}", bucket="channel:get")
        if result.status == 404 or not isinstance(result.data, dict):
            raise DiscordError(404, "Channel not found, or this account cannot see it")
        return result.data

    def search(
        self,
        *,
        channel_id: str,
        author_id: str,
        guild_id: str | None = None,
        offset: int = 0,
        min_id: int | None = None,
        max_id: int | None = None,
    ) -> ApiResult:
        """Search for the account's own messages.

        author_id filters server-side, so other people's messages are never
        transferred at all. Returns the raw ApiResult because a 202 (search
        index warming up) is a normal, retryable outcome the caller handles.
        """
        params: dict[str, Any] = {"author_id": author_id, "offset": offset}
        if min_id is not None:
            params["min_id"] = min_id
        if max_id is not None:
            params["max_id"] = max_id

        if guild_id:
            params["channel_id"] = channel_id
            path = f"/guilds/{guild_id}/messages/search"
            bucket = f"search:guild:{guild_id}"
        else:
            path = f"/channels/{channel_id}/messages/search"
            bucket = f"search:channel:{channel_id}"
        return self.request("GET", path, params=params, bucket=bucket)

    def list_messages(
        self,
        channel_id: str,
        *,
        before: int | str | None = None,
        after: int | str | None = None,
        limit: int = config.MESSAGES_PAGE_SIZE,
    ) -> list[dict]:
        """Plain history pagination - the fallback when search is unavailable."""
        params: dict[str, Any] = {"limit": limit}
        if before is not None:
            params["before"] = str(before)
        if after is not None:
            params["after"] = str(after)
        result = self.request(
            "GET",
            f"/channels/{channel_id}/messages",
            params=params,
            bucket=f"messages:{channel_id}",
        )
        if result.status == 404 or not isinstance(result.data, list):
            return []
        return result.data

    def delete_message(self, channel_id: str, message_id: str) -> int:
        """Delete one message. Returns the HTTP status.

        404 is not an error: the message is already gone, which is the outcome
        we wanted. The caller distinguishes it from a real failure.
        """
        result = self.request(
            "DELETE",
            f"/channels/{channel_id}/messages/{message_id}",
            bucket=f"delete:{channel_id}",
        )
        return result.status


def _safe_json(response) -> Any:
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _get(body: Any, key: str, default=None):
    return body.get(key, default) if isinstance(body, dict) else default


def _retry_after(body: Any, headers: Mapping[str, str]) -> float:
    """Prefer the float seconds in the body over the coarser header value."""
    value = _get(body, "retry_after")
    if value is None:
        value = headers.get("Retry-After")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 5.0


def _error_message(body: Any, status: int) -> str:
    return _get(body, "message") or f"Discord returned HTTP {status}"
