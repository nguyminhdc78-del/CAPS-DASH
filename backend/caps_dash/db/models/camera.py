"""Cameras.

Configuration lives here rather than in a JSON file so cameras can be added and
retuned from the dashboard without editing a file and restarting the system.
The reference project started that migration and never finished it, leaving two
sources of truth; this table is the only one.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, CheckConstraint, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base
from ..enums import CameraSourceType, values
from ..mixins import TimestampMixin
from ..types import UtcDateTime

if TYPE_CHECKING:
    from .parking_slot import ParkingSlot


class Camera(Base, TimestampMixin):
    __tablename__ = "cameras"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ({})".format(
                ", ".join(f"'{v}'" for v in values(CameraSourceType))
            ),
            name="source_type_valid",
        ),
        # A threshold above the window can never be reached: the camera would
        # sit at UNKNOWN forever, with nothing to indicate why.
        CheckConstraint("vote_threshold <= vote_window", name="threshold_within_window"),
        CheckConstraint("vote_window >= 1", name="window_positive"),
        CheckConstraint("poll_interval_s > 0", name="poll_interval_positive"),
        CheckConstraint("confidence > 0 AND confidence < 1", name="confidence_in_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    floor: Mapped[str] = mapped_column(String(16), default="B1", index=True)

    source_type: Mapped[str] = mapped_column(
        String(24), default=CameraSourceType.ESP32CAM_HTTP
    )
    # An IP or URL for a network camera; a path for the folder/video sources.
    source_url: Mapped[str] = mapped_column(String(255), default="")

    # Per-camera tuning. Basement lighting and vehicle mix differ between
    # positions, so a single global value never fits every camera.
    poll_interval_s: Mapped[float] = mapped_column(Float, default=3.0)
    vote_window: Mapped[int] = mapped_column(Integer, default=5)
    vote_threshold: Mapped[int] = mapped_column(Integer, default=4)
    confidence: Mapped[float] = mapped_column(Float, default=0.25)

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Size of the most recent frame. Lets the UI scale a slot map before the
    # first live frame arrives.
    frame_width: Mapped[int] = mapped_column(Integer, default=0)
    frame_height: Mapped[int] = mapped_column(Integer, default=0)

    last_seen_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")

    # Sensor settings this camera SHOULD be running with, re-applied whenever
    # its worker starts. The ESP32 keeps these in RAM only, so a power blip
    # silently reverts the exposure lock to automatic - and an unlocked sensor
    # hunts, which the change gate reads as motion and which takes inference
    # from 11% of frames to nearly all of them. Nothing would report that; the
    # board would just get slower. Persisting the intent is what closes it.
    sensor_settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    slots: Mapped[list[ParkingSlot]] = relationship(
        back_populates="camera",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Camera {self.code} {self.floor}>"
