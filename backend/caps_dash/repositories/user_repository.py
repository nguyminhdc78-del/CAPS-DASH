"""Database access for users and their sessions.

Repositories keep the queries in one place so services read as business logic
rather than SQL. The reference project put queries, mutations, audit writes and
commits inline in every route handler, which is what this separation prevents.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.enums import UserRole
from ..db.models import RefreshSession, User
from ..db.types import utc_now


def get_by_username(session: Session, username: str) -> User | None:
    return session.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()


def get_by_id(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def list_users(session: Session) -> list[User]:
    return list(session.execute(select(User).order_by(User.username)).scalars())


def count_active_admins(session: Session, *, excluding_id: int | None = None) -> int:
    """Used to refuse the change that would lock everyone out of administration."""
    query = select(func.count(User.id)).where(
        User.role == UserRole.ADMIN, User.is_active.is_(True)
    )
    if excluding_id is not None:
        query = query.where(User.id != excluding_id)
    return int(session.execute(query).scalar_one())


# --- Refresh sessions --------------------------------------------------------


def get_session_by_jti(session: Session, jti: str) -> RefreshSession | None:
    return session.execute(
        select(RefreshSession).where(RefreshSession.jti == jti)
    ).scalar_one_or_none()


def list_active_sessions(session: Session, user_id: int) -> list[RefreshSession]:
    now = utc_now()
    query = (
        select(RefreshSession)
        .where(
            RefreshSession.user_id == user_id,
            RefreshSession.revoked_at.is_(None),
            RefreshSession.rotated_at.is_(None),
            RefreshSession.expires_at > now,
        )
        .order_by(RefreshSession.issued_at.desc())
    )
    return list(session.execute(query).scalars())


def revoke_all_sessions(session: Session, user_id: int, *, when: dt.datetime | None = None) -> int:
    """Revoke every live session for a user. Returns how many were closed."""
    moment = when or utc_now()
    rows = session.execute(
        select(RefreshSession).where(
            RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None)
        )
    ).scalars()
    count = 0
    for row in rows:
        row.revoked_at = moment
        count += 1
    return count
