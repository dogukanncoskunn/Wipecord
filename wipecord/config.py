"""Tunable constants for Wipecord.

Everything that governs how hard we hit the Discord API lives here, in one
place, so the pacing policy can be reviewed without reading the transport code.
"""

from __future__ import annotations

API_BASE = "https://discord.com/api/v10"

# An honest User-Agent. Wipecord deliberately does NOT impersonate the official
# Discord client: identifying ourselves is the difference between "a rate-limit
# respecting personal tool" and "an evasion tool".
USER_AGENT = "Wipecord/0.1 (+https://github.com/dogukanncoskunn/Wipecord)"

REQUEST_TIMEOUT = 30.0

# --- Snowflake ---------------------------------------------------------------
# Discord's epoch: 2015-01-01T00:00:00Z, in milliseconds.
DISCORD_EPOCH_MS = 1_420_070_400_000
SNOWFLAKE_TIMESTAMP_SHIFT = 22
# The low 22 bits are worker/process/increment. Setting them all gives the last
# possible snowflake within a given millisecond, which is what an inclusive
# upper bound needs.
SNOWFLAKE_LOW_BITS_MASK = (1 << SNOWFLAKE_TIMESTAMP_SHIFT) - 1

# --- Pacing ------------------------------------------------------------------
# Hard floor. The UI refuses to go below this no matter what the user types:
# a tool that can be configured into a hammer is a tool that gets accounts
# flagged.
DELAY_FLOOR = 1.0
DELAY_CEILING = 60.0
DEFAULT_DELAY_MIN = 1.5
DEFAULT_DELAY_MAX = 3.5

# Every N deletions, take a longer pause. Sustained uniform traffic for an hour
# is a worse pattern than the same traffic broken up.
BREATHER_EVERY = 50
BREATHER_MIN = 15.0
BREATHER_MAX = 30.0

# --- Rate limit handling -----------------------------------------------------
# Added on top of any server-provided wait, so we always resume *after* the
# window rather than exactly on its edge.
RATE_LIMIT_JITTER_MIN = 0.25
RATE_LIMIT_JITTER_MAX = 0.75

# A global 429 is far more serious than a per-route one; back off much harder.
GLOBAL_429_EXTRA = 5.0

# After this many 429s in a row, slow the baseline down.
ADAPTIVE_429_THRESHOLD = 3
ADAPTIVE_FACTOR = 1.5
ADAPTIVE_MAX_MULTIPLIER = 4.0

# After this many 429s in a row, stop entirely. Cloudflare bans an IP after
# ~10,000 failed requests in 10 minutes; a tight retry loop is exactly how
# tools get there. We would rather abort the job than burn the IP.
MAX_CONSECUTIVE_429 = 5

# --- Transport retries -------------------------------------------------------
MAX_TRANSPORT_RETRIES = 3
TRANSPORT_BACKOFF_BASE = 1.0

# --- Discovery ---------------------------------------------------------------
SEARCH_PAGE_SIZE = 25
# Discord refuses search offsets beyond this; past it we slide the window using
# max_id instead of paging further.
SEARCH_MAX_OFFSET = 5000
# Returned with HTTP 202 when the search index is still warming up. Not an error.
SEARCH_INDEX_NOT_READY = 110
# A warming index resolves in seconds. Cap both the individual wait and the
# number of retries so a stuck (or hostile) retry_after cannot park a scan
# forever with nothing on screen.
SEARCH_INDEX_MAX_WAIT = 30.0
SEARCH_INDEX_MAX_ATTEMPTS = 10
MESSAGES_PAGE_SIZE = 100
