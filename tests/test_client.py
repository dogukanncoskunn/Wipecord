import pytest
import requests

from wipecord import config
from wipecord.client import (
    AuthError,
    DiscordClient,
    DiscordError,
    Redactor,
    TransportError,
)
from wipecord.ratelimit import RateLimiter

from conftest import FakeResponse, FakeSession, FakeSleeper

TOKEN = "mfa.aVeryLongLookingFakeTokenValueForTests1234567890"


def build(responses, sleeper=None):
    session = FakeSession(responses)
    limiter = RateLimiter(sleeper=sleeper or FakeSleeper())
    client = DiscordClient(TOKEN, limiter, session=session)
    return client, session


# --- redaction ---------------------------------------------------------------


def test_redactor_scrubs_the_token_from_arbitrary_text():
    redact = Redactor()
    redact.add(TOKEN)
    assert TOKEN not in redact(f"Authorization: {TOKEN} failed")
    assert Redactor.PLACEHOLDER in redact(f"Authorization: {TOKEN} failed")


def test_redactor_ignores_short_strings_that_would_shred_the_log():
    redact = Redactor()
    redact.add("abc")
    redact.add(None)
    assert redact("abc def") == "abc def"


def test_the_client_registers_its_own_token_for_redaction():
    client, _ = build([])
    assert TOKEN not in client.redact(f"boom {TOKEN}")


def test_a_network_error_carrying_the_token_is_redacted_before_it_escapes():
    # requests sometimes embeds the request headers in exception text.
    boom = requests.ConnectionError(f"failed sending Authorization: {TOKEN}")
    client, _ = build([boom] * (config.MAX_TRANSPORT_RETRIES + 1))
    with pytest.raises(TransportError) as exc:
        client.verify_token()
    assert TOKEN not in str(exc.value)


# --- auth headers ------------------------------------------------------------


def test_the_user_token_is_sent_without_a_bot_prefix():
    client, session = build([])
    assert session.headers["Authorization"] == TOKEN
    assert not session.headers["Authorization"].startswith("Bot ")


def test_the_user_agent_identifies_wipecord_rather_than_the_official_client():
    _, session = build([])
    agent = session.headers["User-Agent"]
    assert agent.startswith("Wipecord/")
    assert "Discord" not in agent


# --- rate-limit integration --------------------------------------------------


def test_a_429_is_waited_out_and_the_same_request_is_retried():
    sleeper = FakeSleeper()
    client, session = build(
        [
            FakeResponse(429, {"retry_after": 1.75, "global": False}),
            FakeResponse(200, {"id": "1", "username": "me"}),
        ],
        sleeper,
    )
    assert client.verify_token()["id"] == "1"
    assert len(session.calls) == 2
    assert sleeper.slept[0] > 1.75


def test_the_body_retry_after_wins_over_the_coarser_header():
    sleeper = FakeSleeper()
    client, _ = build(
        [
            # The header rounds up to whole seconds; the body is exact. They are
            # far apart here so jitter cannot blur which one was used.
            FakeResponse(429, {"retry_after": 0.1}, {"Retry-After": "30"}),
            FakeResponse(200, {"id": "1"}),
        ],
        sleeper,
    )
    client.verify_token()
    assert 0.1 < sleeper.slept[0] <= 0.1 + config.RATE_LIMIT_JITTER_MAX


def test_a_429_without_a_json_body_falls_back_to_the_header():
    sleeper = FakeSleeper()
    client, _ = build(
        [
            FakeResponse(429, None, {"Retry-After": "3"}),
            FakeResponse(200, {"id": "1"}),
        ],
        sleeper,
    )
    client.verify_token()
    assert sleeper.slept[0] > 3.0


def test_server_errors_are_retried_then_surface_as_an_error():
    client, session = build([FakeResponse(503)] * (config.MAX_TRANSPORT_RETRIES + 1))
    with pytest.raises(DiscordError):
        client.verify_token()
    assert len(session.calls) == config.MAX_TRANSPORT_RETRIES + 1


def test_network_errors_recover_when_the_connection_comes_back():
    client, session = build(
        [requests.ConnectionError("reset"), FakeResponse(200, {"id": "7"})]
    )
    assert client.verify_token()["id"] == "7"
    assert len(session.calls) == 2


# --- error mapping -----------------------------------------------------------


def test_an_invalid_token_raises_auth_error():
    client, _ = build([FakeResponse(401, {"message": "401: Unauthorized", "code": 0})])
    with pytest.raises(AuthError):
        client.verify_token()


def test_a_forbidden_channel_raises_auth_error():
    client, _ = build([FakeResponse(403, {"message": "Missing Access"})])
    with pytest.raises(AuthError):
        client.get_channel("123")


def test_a_missing_channel_is_reported_as_not_found():
    client, _ = build([FakeResponse(404, {"message": "Unknown Channel"})])
    with pytest.raises(DiscordError) as exc:
        client.get_channel("123")
    assert exc.value.status == 404


# --- endpoint shapes ---------------------------------------------------------


def test_guild_search_scopes_to_the_channel_and_the_authors_own_messages():
    client, session = build([FakeResponse(200, {"total_results": 0, "messages": []})])
    client.search(channel_id="C1", author_id="U1", guild_id="G1")
    method, url, params = session.calls[0]
    assert url.endswith("/guilds/G1/messages/search")
    assert params["author_id"] == "U1"
    assert params["channel_id"] == "C1"


def test_dm_search_uses_the_channel_endpoint_and_omits_guild_scoping():
    client, session = build([FakeResponse(200, {"total_results": 0, "messages": []})])
    client.search(channel_id="C1", author_id="U1")
    _, url, params = session.calls[0]
    assert url.endswith("/channels/C1/messages/search")
    assert "channel_id" not in params


def test_a_date_bounded_search_pushes_the_range_to_the_server():
    client, session = build([FakeResponse(200, {"total_results": 0, "messages": []})])
    client.search(channel_id="C1", author_id="U1", min_id=111, max_id=999)
    _, _, params = session.calls[0]
    assert params["min_id"] == 111
    assert params["max_id"] == 999


def test_a_202_search_response_is_returned_rather_than_raised():
    # Search index warming up is a normal outcome the scanner retries.
    client, _ = build([FakeResponse(202, {"code": 110, "retry_after": 2})])
    result = client.search(channel_id="C1", author_id="U1")
    assert result.status == 202
    assert result.data["code"] == config.SEARCH_INDEX_NOT_READY


def test_deleting_an_already_deleted_message_reports_404_instead_of_raising():
    client, _ = build([FakeResponse(404, {"message": "Unknown Message"})])
    assert client.delete_message("C1", "M1") == 404


def test_a_successful_delete_reports_204():
    client, session = build([FakeResponse(204)])
    assert client.delete_message("C1", "M1") == 204
    method, url, _ = session.calls[0]
    assert method == "DELETE"
    assert url.endswith("/channels/C1/messages/M1")


def test_deletes_are_bucketed_per_channel_the_way_discord_limits_them():
    sleeper = FakeSleeper()
    client, _ = build(
        [
            FakeResponse(204, None, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset-After": "2"}),
            FakeResponse(204),
        ],
        sleeper,
    )
    client.delete_message("C1", "M1")
    client.delete_message("C1", "M2")
    # The exhausted bucket from the first delete is waited out before the second.
    assert sleeper.slept and sleeper.slept[0] > 2.0
