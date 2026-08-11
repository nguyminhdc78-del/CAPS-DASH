"""Operational alerts."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..enums import AlertSeverity, AlertType, values
from ..mixins import ClockSuspectMixin
from ..types import UtcDateTime, utc_now


class Alert(Base, ClockSuspectMixin):
    __tablename__ = "alerts"
    __table_args__ = (
        # The list view is "unacknowledged first, newest first".
        Index("ix_alerts_open_recent", "acknowledged_at", "created_at"),
        CheckConstraint(
            "alert_type IN ({})".format(", ".join(f"'{v}'" for v in values(AlertType))),
            name="alert_type_valid",
        ),
        CheckConstraint(
            "severity IN ({})".format(", ".join(f"'{v}'" for v in values(AlertSeverity))),
            name="severity_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_type: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(16), default=AlertSeverity.WARNING)

    entity_type: Mapped[str] = mapped_column(String(24), default="")
    entity_id: Mapped[str] = mapped_column(String(32), default="")

    # A stable code the frontend localises, plus structured values to fill it.
    # Storing a rendered Vietnamese sentence here would make the alert
    # untranslatable and unsearchable.
    message_code: Mapped[str] = mapped_column(String(64))
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Human-readable fallback for logs and for direct API users.
    message: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utc_now, index=True)
    acknowledged_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    acknowledged_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    @property
    def is_open(self) -> bool:
        return self.acknowledged_at is None
