"""Who changed what, and when.

Only MUTATING actions are recorded. Reads are noise here, and logging them
would bury the one question this table exists to answer.

That question is concrete: when the system reports the wrong slot, the first
thing anyone asks is who last edited the slot map. Without this table there is
no answer.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..mixins import ClockSuspectMixin
from ..types import UtcDateTime, utc_now


class AuditLog(Base, ClockSuspectMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # SET NULL, not CASCADE: deleting a user must not erase the record of what
    # they did. The username is copied below so the trail survives regardless.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    username: Mapped[str] = mapped_column(String(64), default="", index=True)

    action: Mapped[str] = mapped_column(String(32), index=True)
    entity_type: Mapped[str] = mapped_column(String(24), default="")
    entity_id: Mapped[str] = mapped_column(String(32), default="")

    # Before/after snapshots, with secrets stripped by the audit service.
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    client_ip: Mapped[str] = mapped_column(String(64), default="")
    # Ties the row to the server log lines for the same request.
    request_id: Mapped[str] = mapped_column(String(64), default="", index=True)

    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utc_now, index=True)
