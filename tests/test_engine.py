import queue
import threading
import time

import pytest

from wipecord.client import AuthError, DiscordError
from wipecord.engine import DeletionEngine, Job
from wipecord.events import DoneEvent, Level, LogEvent, PreviewEvent, State, StateEvent
from wipecord.ratelimit import RateLimitAbort, RateLimiter
from wipecord.scanner import Mode, ScanCriteria

from conftest import FakeSleeper
from fakes import FakeClient, message, search_page

TOKEN = "mfa.aVeryLongLookingFakeTokenValueForTests1234567890"


def build_engine(client, sleeper=None):
    """An engine wired to a fake client and a limiter that never really sleeps."""
    engine = DeletionEngine(queue.Queue())
    engine._client_factory = lambda token, limiter, redactor: client
    engine._limiter_factory = lambda job, stop, notify: RateLimiter(
        sleeper=sleeper or FakeSleeper(), notify=notify
    )
    return engine


def run(engine, job, timeout=10):
    engine.start(job)
    engine.join(timeout)
    assert not engine.busy, "worker did not finish"
    return drain(engine)


def drain(engine):
    events = []
    while True:
        try:
            events.append(engine.events.get_nowait())
        except queue.Empty:
            return events


def pick(events, kind):
    return [e for e in events if isinstance(e, kind)]


def summary_of(events):
    done = pick(events, DoneEvent)
    assert done, "no DoneEvent emitted"
    return done[-1].summary


def job(**kwargs):
    return Job(token=TOKEN, channel_id="C1", **kwargs)


def client_with(count=5, **kwargs):
    return FakeClient(
        search_pages=[search_page([message(str(i)) for i in range(1, count + 1)], total=count)],
        **kwargs,
    )


# --- dry run -----------------------------------------------------------------


def test_a_dry_run_deletes_nothing_at_all():
    client = client_with(5)
    events = run(build_engine(client), job(dry_run=True))
    assert client.deleted == []
    assert summary_of(events).scanned == 5
    assert summary_of(events).deleted == 0


def test_a_dry_run_reports_exactly_what_would_be_removed():
    client = client_with(3)
    events = run(build_engine(client), job(dry_run=True))
    preview = pick(events, PreviewEvent)[-1]
    assert [ref.id for ref in preview.messages] == ["1", "2", "3"]
    assert preview.channel_label == "#general"


def test_a_dry_run_never_enters_the_deleting_state():
    events = run(build_engine(client_with(3)), job(dry_run=True))
    states = [e.state for e in pick(events, StateEvent)]
    assert State.SCANNING in states
    assert State.DELETING not in states


# --- deleting ----------------------------------------------------------------


def test_a_real_run_deletes_every_message_it_found():
    client = client_with(4)
    events = run(build_engine(client), job(dry_run=False))
    assert client.deleted == ["1", "2", "3", "4"]
    assert summary_of(events).deleted == 4


def test_other_peoples_messages_are_never_deleted():
    client = FakeClient(
        search_pages=[
            search_page(
                [
                    message("1", author_id="ME"),
                    message("2", author_id="SOMEONE_ELSE"),
                    message("3", author_id="ME"),
                ],
                total=3,
            )
        ]
    )
    run(build_engine(client), job(dry_run=False))
    assert client.deleted == ["1", "3"]


def test_last_n_deletes_only_that_many():
    client = client_with(20)
    run(
        build_engine(client),
        job(dry_run=False, criteria=ScanCriteria(mode=Mode.LAST_N, limit=6)),
    )
    assert len(client.deleted) == 6


def test_an_already_deleted_message_counts_as_skipped_not_failed():
    client = client_with(3, delete_results={"2": 404})
    result = summary_of(run(build_engine(client), job(dry_run=False)))
    assert (result.deleted, result.skipped, result.failed) == (2, 1, 0)


def test_one_forbidden_message_does_not_abandon_the_rest():
    client = client_with(3, delete_results={"2": AuthError(403, "Missing Access")})
    result = summary_of(run(build_engine(client), job(dry_run=False)))
    assert result.failed == 1
    assert result.deleted == 2
    assert client.deleted == ["1", "2", "3"]


def test_a_per_message_api_error_is_recorded_and_the_run_continues():
    client = client_with(3, delete_results={"1": DiscordError(400, "bad request")})
    result = summary_of(run(build_engine(client), job(dry_run=False)))
    assert result.failed == 1
    assert result.deleted == 2


def test_the_client_is_closed_even_after_a_failure():
    client = client_with(1, delete_results={"1": DiscordError(500, "boom")})
    run(build_engine(client), job(dry_run=False))
    assert client.closed is True


# --- pause, resume, stop -----------------------------------------------------


def test_pausing_halts_progress_until_resumed():
    client = client_with(30)
    engine = build_engine(client)
    reached = threading.Event()

    def on_delete(message_id):
        if len(client.deleted) == 2 and not reached.is_set():
            engine.pause()
            reached.set()

    client.on_delete = on_delete
    engine.start(job(dry_run=False))
    assert reached.wait(5)

    time.sleep(0.4)
    frozen = len(client.deleted)
    time.sleep(0.4)
    assert len(client.deleted) == frozen, "work continued while paused"
    assert engine.paused

    engine.resume()
    engine.join(10)
    assert len(client.deleted) == 30


def test_stopping_ends_the_run_early_and_says_so():
    client = client_with(50)
    engine = build_engine(client)

    def on_delete(message_id):
        if len(client.deleted) == 3:
            engine.stop()

    client.on_delete = on_delete
    engine.start(job(dry_run=False))
    engine.join(10)
    assert not engine.busy
    assert len(client.deleted) < 50
    assert summary_of(drain(engine)).stopped is True


def test_stopping_while_paused_unwinds_instead_of_hanging():
    # A paused worker is parked on the running event; Stop must release it.
    client = client_with(40)
    engine = build_engine(client)
    reached = threading.Event()

    def on_delete(message_id):
        if len(client.deleted) == 2:
            engine.pause()
            reached.set()

    client.on_delete = on_delete
    engine.start(job(dry_run=False))
    assert reached.wait(5)
    time.sleep(0.3)
    engine.stop()
    engine.join(5)
    assert not engine.busy


def test_a_second_job_cannot_start_while_one_is_running():
    gate = threading.Event()

    class BlockingClient(FakeClient):
        def verify_token(self):
            gate.wait(5)
            return super().verify_token()

    engine = build_engine(BlockingClient(search_pages=[search_page([], total=0)]))
    engine.start(job())
    try:
        assert engine.busy
        with pytest.raises(RuntimeError):
            engine.start(job())
    finally:
        gate.set()
        engine.join(5)


# --- failures ----------------------------------------------------------------


def test_an_invalid_token_reports_cleanly_instead_of_crashing():
    class BadClient(FakeClient):
        def verify_token(self):
            raise AuthError(401, "401: Unauthorized")

    events = run(build_engine(BadClient()), job())
    result = summary_of(events)
    assert result.error is not None
    assert any(e.level is Level.ERROR for e in pick(events, LogEvent))


def test_an_unreachable_channel_reports_cleanly():
    client = FakeClient(channel=DiscordError(404, "Unknown Channel"))
    result = summary_of(run(build_engine(client), job()))
    assert result.error is not None


def test_a_rate_limit_abort_stops_the_run_with_an_explanation():
    class AbortingClient(FakeClient):
        def delete_message(self, channel_id, message_id):
            raise RateLimitAbort("5 consecutive rate limits")

    client = AbortingClient(
        search_pages=[search_page([message("1"), message("2")], total=2)]
    )
    events = run(build_engine(client), job(dry_run=False))
    assert "rate limit" in summary_of(events).error.lower()
    assert any("Wait a few minutes" in e.text for e in pick(events, LogEvent))


def test_an_unexpected_error_is_contained_rather_than_killing_the_thread():
    class ExplodingClient(FakeClient):
        def verify_token(self):
            raise ValueError("something nobody predicted")

    events = run(build_engine(ExplodingClient()), job())
    assert summary_of(events).error is not None
    assert any("Unexpected error" in e.text for e in pick(events, LogEvent))


# --- secrets -----------------------------------------------------------------


def test_the_token_never_appears_in_any_emitted_event():
    class LeakyClient(FakeClient):
        def verify_token(self):
            raise DiscordError(400, f"request failed with Authorization: {TOKEN}")

    events = run(build_engine(LeakyClient()), job())
    text = " ".join(e.text for e in pick(events, LogEvent))
    assert TOKEN not in text
    assert "REDACTED" in text


def test_the_token_is_absent_from_a_normal_successful_run():
    events = run(build_engine(client_with(2)), job(dry_run=False))
    text = " ".join(e.text for e in pick(events, LogEvent))
    assert TOKEN not in text


# --- reporting ---------------------------------------------------------------


def test_the_run_always_ends_with_a_done_event():
    for dry in (True, False):
        events = run(build_engine(client_with(2)), job(dry_run=dry))
        assert len(pick(events, DoneEvent)) == 1
        assert summary_of(events).duration >= 0


def test_deletions_are_logged_with_a_readable_summary():
    client = FakeClient(
        search_pages=[search_page([message("1", content="hello world")], total=1)]
    )
    events = run(build_engine(client), job(dry_run=False))
    deletes = [e for e in pick(events, LogEvent) if e.level is Level.DELETE]
    assert any("hello world" in e.text for e in deletes)


def test_the_wait_between_deletions_is_shown_to_the_user():
    events = run(build_engine(client_with(3)), job(dry_run=False))
    waits = [e for e in pick(events, LogEvent) if e.level is Level.WAIT]
    assert waits, "no waiting feedback was emitted"
    assert any("Waiting" in e.text for e in waits)


def test_no_wait_is_announced_after_the_final_deletion():
    events = run(build_engine(client_with(1)), job(dry_run=False))
    waits = [e for e in pick(events, LogEvent) if e.level is Level.WAIT]
    assert waits == []
