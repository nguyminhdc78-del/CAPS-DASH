"""Slot state transitions - the source every report derives from.

TWO DESIGN DECISIONS WORTH DEFENDING

1. Rows are written ONLY when a state CHANGES, never once per scan.
   A 100-slot site scanned every second would produce 8.6 million rows a day,
   filling the disk and wearing out flash storage for no added information.
   On-change writing produces a few hundred and loses nothing.

2. There is no `parking_session` table.
   A session is two consecutive rows here: OCCUPIED then FREE. Storing it
   separately duplicates state, and the two copies will disagree the first time
   anything goes wrong - at which point nobody can tell which one to believe.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..enums import SlotState, values
from ..mixins import ClockSuspectMixin
from ..types import UtcDateTime, utc_now


class SlotStateHistory(Base, ClockSuspectMixin):
    __tablename__ = "slot_state_history"
    __table_args__ = (
        # Reports always filter by slot and time range, in that order.
        Index("ix_slot_state_history_slot_time", "slot_id", "changed_at"),
        # Site-wide reports filter by time alone.
        Index("ix_slot_state_history_time", "changed_at"),
        CheckConstraint(
            "new_state IN ({})".format(", ".join(f"'{v}'" for v in values(SlotState))),
            name="new_state_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slot_id: Mapped[int] = mapped_column(
        ForeignKey("parking_slots.id", ondelete="CASCADE"), index=True
    )

    # Denormalised so per-camera range queries need no join. Worth the
    # duplication: this is the largest table and the join is on its hot path.
    camera_code: Mapped[str] = mapped_column(String(16), index=True)
    slot_code: Mapped[str] = mapped_column(String(16))
    floor: Mapped[str] = mapped_column(String(16), default="B1", index=True)

    previous_state: Mapped[str] = mapped_column(String(16), default=SlotState.UNKNOWN)
    new_state: Mapped[str] = mapped_column(String(16))
    changed_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utc_now)
