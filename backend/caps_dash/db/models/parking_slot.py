"""Parking slots and their polygons."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base
from ..enums import SlotState, values
from ..mixins import TimestampMixin
from ..types import UtcDateTime

if TYPE_CHECKING:
    from .camera import Camera


class ParkingSlot(Base, TimestampMixin):
    __tablename__ = "parking_slots"
    __table_args__ = (
        UniqueConstraint("camera_id", "code", name="code_unique_per_camera"),
        CheckConstraint(
            "current_state IN ({})".format(", ".join(f"'{v}'" for v in values(SlotState))),
            name="state_valid",
        ),
        CheckConstraint("src_frame_width > 0", name="src_width_positive"),
        CheckConstraint("src_frame_height > 0", name="src_height_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[int] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(16), index=True)
    floor: Mapped[str] = mapped_column(String(16), default="B1", index=True)

    # [[x, y], ...] in the pixel coordinates of the frame the polygon was drawn
    # on. Stored as JSON because it is opaque to SQL - nothing ever queries
    # inside it.
    polygon_json: Mapped[list[Any]] = mapped_column(JSON, default=list)

    # The dimensions of THAT frame. Without them the polygon cannot be mapped
    # onto a live frame of a different size, and the two axis scale factors
    # cannot be computed independently - the failure that silently reports
    # every slot free forever.
    src_frame_width: Mapped[int] = mapped_column(Integer, default=640)
    src_frame_height: Mapped[int] = mapped_column(Integer, default=480)

    current_state: Mapped[str] = mapped_column(
        String(16), default=SlotState.UNKNOWN, index=True
    )
    # When the current state began. Drives overstay alerts and lets the UI show
    # a duration without querying history.
    state_since: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    camera: Mapped[Camera] = relationship(back_populates="slots")

    def __repr__(self) -> str:
        return f"<ParkingSlot {self.code} {self.current_state}>"
