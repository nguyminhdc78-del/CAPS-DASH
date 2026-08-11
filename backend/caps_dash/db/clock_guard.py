"""Is the system clock trustworthy?

The target hardware has no battery-backed real-time clock. After a power cut it
boots believing it is some date in the past, and every row written before NTP
catches up carries a wrong timestamp.

Rather than silently miscount those rows in reports, they are flagged. A report
can then exclude them and say so, which is honest; quietly averaging them in is
not. The dashboard surfaces the condition instead of hiding it.
"""

from __future__ import annotations

import datetime as dt

from .types import utc_now

# Any clock reading earlier than this is certainly wrong: it predates the
# project. Bump it on a major release, never below the previous value.
MIN_PLAUSIBLE_DATE = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)

# Far-future readings are equally impossible and equally damaging to reports.
MAX_PLAUSIBLE_YEARS_AHEAD = 5


def is_clock_suspect(now: dt.datetime | None = None) -> bool:
    """True when timestamps written right now should not be trusted."""
    current = now or utc_now()
    if current < MIN_PLAUSIBLE_DATE:
        return True
    horizon = MIN_PLAUSIBLE_DATE.replace(
        year=MIN_PLAUSIBLE_DATE.year + MAX_PLAUSIBLE_YEARS_AHEAD
    )
    return current > horizon
