"""Conversions between datetimes and Discord snowflake IDs.

A snowflake embeds its own creation timestamp, which means a date range can be
expressed as an ID range and pushed to the server (`min_id`/`max_id` on search,
`after`/`before` on the messages endpoint). That is why date filtering in
Wipecord costs no extra requests and is exact rather than approximate.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from .config import (
    DISCORD_EPOCH_MS,
    SNOWFLAKE_LOW_BITS_MASK,
    SNOWFLAKE_TIMESTAMP_SHIFT,
)


def _as_utc(dt: datetime) -> datetime:
    """Return `dt` in UTC, treating a naive datetime as local time.

    Users think in the timestamps Discord shows them, which are local, so a
    naive input is interpreted the same way rather than as UTC.
    """
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(timezone.utc)


def datetime_to_snowflake(dt: datetime, *, inclusive_end: bool = False) -> int:
    """Convert a datetime to the first (or last) snowflake of that millisecond.

    `inclusive_end=True` fills the low bits, giving an upper bound that includes
    every message created during that millisecond.
    """
    ms = int(_as_utc(dt).timestamp() * 1000)
    delta = ms - DISCORD_EPOCH_MS
    if delta <= 0:
        return SNOWFLAKE_LOW_BITS_MASK if inclusive_end else 0
    snowflake = delta << SNOWFLAKE_TIMESTAMP_SHIFT
    return snowflake | SNOWFLAKE_LOW_BITS_MASK if inclusive_end else snowflake


def snowflake_to_datetime(snowflake: int | str) -> datetime:
    """Recover the UTC creation time encoded in a snowflake."""
    value = int(snowflake)
    ms = (value >> SNOWFLAKE_TIMESTAMP_SHIFT) + DISCORD_EPOCH_MS
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def date_range_to_snowflakes(start: date | None, end: date | None) -> tuple[int | None, int | None]:
    """Turn an inclusive local-time date range into (min_id, max_id).

    Either bound may be None for an open-ended range. The end date covers the
    whole day, up to 23:59:59.999 local time.
    """
    min_id = None
    max_id = None
    if start is not None:
        min_id = datetime_to_snowflake(datetime.combine(start, time.min))
    if end is not None:
        max_id = datetime_to_snowflake(
            datetime.combine(end, time(23, 59, 59, 999_000)), inclusive_end=True
        )
    return min_id, max_id
