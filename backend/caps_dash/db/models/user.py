"""User accounts."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base
from ..enums import UserRole, values
from ..mixins import TimestampMixin
from ..types import UtcDateTime

if TYPE_CHECKING:
    from .refresh_session import RefreshSession


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ({})".format(", ".join(f"'{v}'" for v in values(UserRole))),
            name="role_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Always a hash, never a password. Argon2id encodes its parameters in the
    # string, so the column has to be roomy enough for future re-tuning.
    password_hash: Mapped[str] = mapped_column(String(255))

    display_name: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(16), default=UserRole.RESIDENT, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Global kill-switch. Bumping this invalidates every token ever issued to
    # this user in one write - useful when an account is compromised or
    # disabled, and cheaper than walking the session table.
    token_version: Mapped[int] = mapped_column(Integer, default=0)

    last_login_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)

    sessions: Mapped[list[RefreshSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"
