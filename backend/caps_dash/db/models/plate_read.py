"""Licence plates read at the moment a slot filled.

WHY A TABLE AND NOT A COLUMN ON `parking_slots`

A column would hold "the plate currently in this bay" and nothing else. The
question a guard actually asks is "where is 30H-832.31?", and a car that moved
bays this morning would then be unfindable the moment it moved again. Rows
answer both: the newest row per slot is the current occupant, and the history
is what makes a search useful rather than a snapshot.

WHY THE READ IS STORED EVEN WHEN IT IS PROBABLY WRONG

`confidence` and `plate_width_px` are stored beside the text rather than used
to discard it. A guard looking at a search result can see that a plate was
read at 62 px with 0.31 confidence and treat it accordingly; a filter applied
before storage throws that judgement away and leaves them with silence
instead. The reader already refuses anything below a floor - what survives
here is worth showing with its provenance attached.

PRIVACY. A plate identifies a vehicle and, through it, a person. This table
is read by two routes with different access controls:

1. `/api/plates/search` (authenticated, security-and-above, full details
   including confidence and pixel width) - audited with username.
2. `/api/public/plates/search` (unauthenticated, rate-limited per IP, narrow
   projection: plate+slot+floor+read_at only) - audited anonymously with
   client IP.

All reads are purged on the same retention schedule as occupancy history.
The authenticated dashboard's promise that residents are never shown which bay
holds which car is still kept by the RBAC gate on the staff route. The public
kiosk is a deliberate, separate trade-off documented in `project-overview-pdr.md`.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import UtcDateTime, utc_now


class PlateRead(Base):
    __tablename__ = "plate_reads"
    __table_args__ = (
        # The search: "which bay is this plate in?" - by plate, newest first.
        Index("ix_plate_reads_plate_time", "plate", "read_at"),
        # The reverse: "what is in this bay?" - and the retention purge, which
        # sweeps by time.
        Index("ix_plate_reads_slot_time", "slot_id", "read_at"),
        CheckConstraint("plate <> ''", name="plate_not_empty"),
        CheckConstraint("plate_width_px > 0", name="plate_width_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slot_id: Mapped[int] = mapped_column(
        ForeignKey("parking_slots.id", ondelete="CASCADE"), index=True
    )
    camera_id: Mapped[int] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), index=True
    )

    # Normalised: upper case, letters and digits only. `30H-832.31` is stored
    # as `30H83231`, because the separators are a rendering convention that
    # varies by plate and would otherwise make search depend on how a guard
    # chose to type the punctuation.
    plate: Mapped[str] = mapped_column(String(16), index=True)

    # How sure the detector was, and how many pixels wide the plate was. Kept
    # so a doubtful read can be recognised as doubtful rather than trusted
    # equally with a clear one.
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    plate_width_px: Mapped[int] = mapped_column(Integer, default=0)

    read_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utc_now, index=True)

    def __repr__(self) -> str:
        return f"<PlateRead {self.plate} slot={self.slot_id}>"
