from datetime import date, datetime, timezone

from wipecord.config import SNOWFLAKE_LOW_BITS_MASK
from wipecord.snowflake import (
    date_range_to_snowflakes,
    datetime_to_snowflake,
    snowflake_to_datetime,
)


def test_decodes_the_snowflake_from_discords_own_documentation():
    # Discord documents this ID as created at 2016-04-30T11:18:25.796Z.
    assert snowflake_to_datetime(175928847299117063) == datetime(
        2016, 4, 30, 11, 18, 25, 796000, tzinfo=timezone.utc
    )


def test_round_trips_an_aware_datetime_to_the_millisecond():
    moment = datetime(2024, 3, 15, 9, 30, 45, 123000, tzinfo=timezone.utc)
    assert snowflake_to_datetime(datetime_to_snowflake(moment)) == moment


def test_inclusive_end_fills_the_low_bits():
    moment = datetime(2024, 3, 15, tzinfo=timezone.utc)
    start = datetime_to_snowflake(moment)
    end = datetime_to_snowflake(moment, inclusive_end=True)
    assert end - start == SNOWFLAKE_LOW_BITS_MASK
    # Both still decode to the same millisecond.
    assert snowflake_to_datetime(end) == snowflake_to_datetime(start)


def test_dates_before_the_discord_epoch_clamp_instead_of_going_negative():
    ancient = datetime(2000, 1, 1, tzinfo=timezone.utc)
    assert datetime_to_snowflake(ancient) == 0
    assert datetime_to_snowflake(ancient, inclusive_end=True) == SNOWFLAKE_LOW_BITS_MASK


def test_date_range_covers_the_whole_final_day():
    min_id, max_id = date_range_to_snowflakes(date(2024, 1, 10), date(2024, 1, 12))
    assert min_id is not None and max_id is not None
    assert min_id < max_id
    span = snowflake_to_datetime(max_id) - snowflake_to_datetime(min_id)
    # Three inclusive days, minus the last millisecond.
    assert 2.99 < span.total_seconds() / 86400 < 3.0


def test_date_range_bounds_are_independently_optional():
    assert date_range_to_snowflakes(None, None) == (None, None)
    min_id, max_id = date_range_to_snowflakes(date(2024, 1, 10), None)
    assert min_id is not None and max_id is None
    min_id, max_id = date_range_to_snowflakes(None, date(2024, 1, 10))
    assert min_id is None and max_id is not None


def test_naive_datetimes_are_read_as_local_time():
    # Users type the timestamps Discord shows them, which are local.
    naive = datetime(2024, 6, 1, 12, 0, 0)
    aware = naive.astimezone()
    assert datetime_to_snowflake(naive) == datetime_to_snowflake(aware)
