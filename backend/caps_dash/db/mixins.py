"""Column mixins shared across models."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean
from sqlalchemy.orm import Mapped, mapped_column

from .clock_guard import is_clock_suspect
from .types import UtcDateTime, utc_now


class TimestampMixin:
    """`created_at` / `updated_at`, always tz-aware UTC."""

    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utc_now)
    updated_at: Mapped[dt.datetime] = mapped_column(
        UtcDateTime, default=utc_now, onupdate=utc_now
    )


class ClockSuspectMixin:
    """Marks rows written while the clock could not be trusted.

    Applied to time-series tables only - the ones whose whole value is their
    timestamp. See `clock_guard`.
    """

    clock_suspect: Mapped[bool] = mapped_column(
        Boolean, default=is_clock_suspect, index=True
    )
