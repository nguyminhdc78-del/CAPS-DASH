"""Pre-aggregated hourly occupancy.

Recomputing a year-long report from raw history on the target board's CPU is
too slow to be usable. An hourly job rolls the history forward into this table
once, and reports read from here.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..enums import ScopeType, values
from ..mixins import ClockSuspectMixin
from ..types import UtcDateTime


class HourlyStat(Base, ClockSuspectMixin):
    __tablename__ = "hourly_stats"
    __table_args__ = (
        UniqueConstraint(
            "scope_type", "scope_key", "hour_start", name="scope_hour_unique"
        ),
        CheckConstraint(
            "scope_type IN ({})".format(", ".join(f"'{v}'" for v in values(ScopeType))),
            name="scope_type_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # scope_type/scope_key together identify what is summarised: one slot, one
    # floor, or the whole site. One table instead of three keeps the
    # aggregation job and the reporting queries single-shaped.
    scope_type: Mapped[str] = mapped_column(String(8), index=True)
    scope_key: Mapped[str] = mapped_column(String(32), default="", index=True)

    hour_start: Mapped[dt.datetime] = mapped_column(UtcDateTime, index=True)

    # Seconds, not percentages: percentages cannot be re-aggregated into a
    # daily or weekly figure without the underlying durations.
    occupied_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    free_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    unknown_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    change_count: Mapped[int] = mapped_column(Integer, default=0)
    peak_occupied: Mapped[int] = mapped_column(Integer, default=0)
    slot_count: Mapped[int] = mapped_column(Integer, default=0)
