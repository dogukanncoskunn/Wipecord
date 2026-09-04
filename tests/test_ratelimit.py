import threading

import pytest

from wipecord import config
from wipecord.ratelimit import (
    Bucket,
    RateLimitAbort,
    RateLimiter,
    Sleeper,
    Stopped,
)

from conftest import FakeSleeper


def make_limiter(sleeper=None, rng=None, notify=None, **kwargs):
    return RateLimiter(
        sleeper=sleeper or FakeSleeper(),
        rng=rng,
        notify=notify,
        **kwargs,
    )


# --- interruptible sleeping --------------------------------------------------


def test_sleeper_returns_immediately_when_already_stopped():
    stop = threading.Event()
    stop.set()
    assert Sleeper(stop).sleep(30) is False


def test_a_stop_cuts_a_long_sleep_short():
    stop = threading.Event()
    sleeper = Sleeper(stop)
    timer = threading.Timer(0.05, stop.set)
    timer.start()
    try:
        # A 30s breather must not actually take 30s once Stop is pressed.
        assert sleeper.sleep(30) is False
    finally:
        timer.cancel()


def test_limiter_raises_stopped_when_the_sleep_is_interrupted():
    limiter = make_limiter(FakeSleeper(stop_at=1))
    with pytest.raises(Stopped):
        limiter.sleep(5)


# --- pacing ------------------------------------------------------------------


def test_delay_stays_inside_the_configured_range():
    limiter = make_limiter(delay_min=1.5, delay_max=3.5)
    for _ in range(200):
        assert 1.5 <= limiter.next_delay() <= 3.5


def test_delay_floor_is_enforced_against_an_abusive_setting():
    limiter = make_limiter(delay_min=0.0, delay_max=0.01)
    assert limiter.delay_min == config.DELAY_FLOOR
    assert limiter.next_delay() >= config.DELAY_FLOOR


def test_an_inverted_range_is_repaired_rather_than_crashing():
    limiter = make_limiter(delay_min=5.0, delay_max=2.0)
    assert limiter.delay_max >= limiter.delay_min


def test_breather_sleeps_within_the_configured_window():
    sleeper = FakeSleeper()
    make_limiter(sleeper).breather()
    assert config.BREATHER_MIN <= sleeper.slept[0] <= config.BREATHER_MAX


# --- proactive bucket tracking -----------------------------------------------


def test_an_exhausted_bucket_is_waited_out_before_the_next_request():
    sleeper = FakeSleeper()
    limiter = make_limiter(sleeper)
    limiter.observe("del", 200, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset-After": "4.5"})
    limiter.before_request("del")
    # The server-provided reset plus jitter, so we resume after the window.
    assert 4.5 < sleeper.slept[0] <= 4.5 + config.RATE_LIMIT_JITTER_MAX


def test_a_bucket_with_headroom_does_not_wait():
    sleeper = FakeSleeper()
    limiter = make_limiter(sleeper)
    limiter.observe("del", 200, {"X-RateLimit-Remaining": "3", "X-RateLimit-Reset-After": "4.5"})
    limiter.before_request("del")
    assert sleeper.slept == []


def test_unknown_buckets_do_not_wait():
    sleeper = FakeSleeper()
    make_limiter(sleeper).before_request("never-seen")
    assert sleeper.slept == []


def test_bucket_wait_shrinks_as_time_passes():
    bucket = Bucket(remaining=0, reset_after=10.0, observed_at=100.0)
    assert bucket.wait_needed(now=104.0) == pytest.approx(6.0)
    assert bucket.wait_needed(now=115.0) == 0.0


def test_headerless_responses_leave_bucket_state_untouched():
    limiter = make_limiter()
    limiter.observe("del", 200, {})
    assert "del" not in limiter._buckets


# --- 429 handling ------------------------------------------------------------


def test_retry_after_is_honoured_with_jitter_on_top():
    sleeper = FakeSleeper()
    limiter = make_limiter(sleeper)
    waited = limiter.handle_429("del", 2.5)
    assert 2.5 < waited <= 2.5 + config.RATE_LIMIT_JITTER_MAX
    assert sleeper.slept == [waited]


def test_a_global_rate_limit_backs_off_much_harder():
    limiter = make_limiter()
    assert limiter.handle_429("del", 2.0, is_global=True) > 2.0 + config.GLOBAL_429_EXTRA


def test_repeated_rate_limits_slow_the_baseline_down():
    limiter = make_limiter(delay_min=2.0, delay_max=4.0)
    before = limiter.effective_range
    for _ in range(config.ADAPTIVE_429_THRESHOLD):
        limiter.handle_429("del", 0.1)
    assert limiter.multiplier > 1.0
    assert limiter.effective_range[0] > before[0]


def test_the_streak_aborts_before_it_can_earn_an_ip_ban():
    limiter = make_limiter()
    with pytest.raises(RateLimitAbort):
        for _ in range(config.MAX_CONSECUTIVE_429):
            limiter.handle_429("del", 0.1)


def test_a_successful_response_clears_the_streak():
    limiter = make_limiter()
    limiter.handle_429("del", 0.1)
    limiter.handle_429("del", 0.1)
    assert limiter.consecutive_429 == 2
    limiter.observe("del", 200, {})
    assert limiter.consecutive_429 == 0


def test_a_server_error_does_not_clear_the_streak():
    # 5xx means "try again", not "you are behaving"; keeping the streak means a
    # flapping endpoint still trips the abort.
    limiter = make_limiter()
    limiter.handle_429("del", 0.1)
    limiter.observe("del", 503, {})
    assert limiter.consecutive_429 == 1


def test_a_429_invalidates_the_stale_bucket_reading():
    limiter = make_limiter()
    limiter.observe("del", 200, {"X-RateLimit-Remaining": "5", "X-RateLimit-Reset-After": "1"})
    limiter.handle_429("del", 0.1)
    assert "del" not in limiter._buckets


def test_stop_during_a_rate_limit_wait_propagates():
    limiter = make_limiter(FakeSleeper(stop_at=1))
    with pytest.raises(Stopped):
        limiter.handle_429("del", 3.0)


# --- transport backoff -------------------------------------------------------


def test_transport_backoff_grows_exponentially():
    sleeper = FakeSleeper()
    limiter = make_limiter(sleeper)
    for attempt in (1, 2, 3):
        limiter.transport_backoff(attempt)
    # Each attempt doubles the base wait; jitter only ever adds on top of it.
    for waited, expected_base in zip(sleeper.slept, (1.0, 2.0, 4.0)):
        assert expected_base < waited <= expected_base + config.RATE_LIMIT_JITTER_MAX


# --- notification seam -------------------------------------------------------


def test_waits_are_reported_to_the_caller_for_logging():
    seen = []
    limiter = make_limiter(notify=lambda kind, seconds, detail: seen.append((kind, seconds)))
    limiter.handle_429("del", 1.0)
    limiter.handle_429("del", 1.0, is_global=True)
    limiter.breather()
    limiter.transport_backoff(1)
    assert [kind for kind, _ in seen] == ["ratelimit", "global", "breather", "transport"]
    assert all(seconds > 0 for _, seconds in seen)
