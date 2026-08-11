"""Custom column types."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import DateTime, Dialect, TypeDecorator


class UtcDateTime(TypeDecorator[dt.datetime]):
    """A timestamp that is timezone-aware UTC on both sides of the database.

    SQLite has no timestamp type and hands back naive datetimes, which then get
    compared against aware ones and raise - or worse, get silently treated as
    local time and shift every report by the UTC offset.

    Naive input is REJECTED rather than assumed to be UTC. Guessing here is how
    a system ends up with a mix of local and UTC rows that nobody can untangle
    afterwards.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: dt.datetime | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                "naive datetime rejected; use datetime.now(UTC), not datetime.utcnow()"
            )
        return value.astimezone(dt.UTC).replace(tzinfo=None)

    def process_result_value(self, value: Any, dialect: Dialect) -> dt.datetime | None:
        if value is None:
            return None
        stored: dt.datetime = value
        # SQLite has no timestamp type, so what comes back is naive. It was
        # stored as UTC, so label it rather than let it be compared against
        # aware values (raises) or read as local time (silently wrong).
        if stored.tzinfo is None:
            return stored.replace(tzinfo=dt.UTC)
        return stored.astimezone(dt.UTC)


def utc_now() -> dt.datetime:
    """The only sanctioned clock call. Never `datetime.utcnow()` - it is naive."""
    return dt.datetime.now(dt.UTC)
