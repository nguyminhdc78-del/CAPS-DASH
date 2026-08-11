"""One row per logged-in device.

Chosen over storing a single rotating token id on the user row. A guard
realistically holds a desk PC and a phone at once, and having the second login
silently evict the first is the kind of behaviour people work around by sharing
accounts.

Per-row storage also makes the security story better, not worse: sessions can
be listed and revoked individually, and reuse of an already-rotated token is
detectable per device.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base
from ..types import UtcDateTime, utc_now

if TYPE_CHECKING:
    from .user import User


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"
    __table_args__ = (
        Index("ix_refresh_sessions_user_active", "user_id", "revoked_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # The refresh token's JTI claim. The token itself is never stored - holding
    # it would turn a database read into a full account takeover.
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    issued_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utc_now)
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)

    # Set when this session's token was rotated. If a token bearing a rotated
    # JTI is presented again, it was replayed - treat as theft and revoke the
    # user's whole set.
    rotated_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)

    # Shown in "your active sessions" so a user can recognise their own devices.
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    client_ip: Mapped[str] = mapped_column(String(64), default="")

    user: Mapped[User] = relationship(back_populates="sessions")

    def is_usable(self, now: dt.datetime | None = None) -> bool:
        moment = now or utc_now()
        return self.revoked_at is None and self.rotated_at is None and self.expires_at > moment
