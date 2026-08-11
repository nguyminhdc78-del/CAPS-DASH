"""User administration."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..db.enums import AuditAction, UserRole
from ..db.models import User
from ..errors.codes import ErrorCode
from ..errors.exceptions import AuthError, ConflictError, NotFoundError, ValidationFailedError
from ..repositories import user_repository
from ..security.password_hasher import hash_password, verify_password
from . import audit_service

MIN_PASSWORD_LENGTH = 10


def create_user(
    session: Session,
    *,
    username: str,
    password: str,
    display_name: str,
    role: UserRole,
    actor: User | None = None,
) -> User:
    username = username.strip().lower()
    _validate_password(password)

    if user_repository.get_by_username(session, username) is not None:
        raise ConflictError(f"Username {username!r} is already taken")

    user = User(
        username=username,
        password_hash=hash_password(password),
        display_name=display_name.strip(),
        role=role,
    )
    session.add(user)
    session.flush()  # assign the id before the audit row references it

    audit_service.record(
        session,
        action=AuditAction.USER_CREATED,
        username=actor.username if actor else "",
        user_id=actor.id if actor else None,
        entity_type="user",
        entity_id=str(user.id),
        after={"username": user.username, "role": user.role},
    )
    session.commit()
    return user


def update_user(
    session: Session,
    user_id: int,
    *,
    display_name: str | None = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
    actor: User | None = None,
) -> User:
    user = user_repository.get_by_id(session, user_id)
    if user is None:
        raise NotFoundError(f"No user with id {user_id}")

    before = {"display_name": user.display_name, "role": user.role, "is_active": user.is_active}

    # Refuse the change that would leave nobody able to administer the system.
    # Recovering from that needs shell access to the board, which in a
    # basement security room may mean a site visit.
    losing_admin = (role is not None and role != UserRole.ADMIN) or is_active is False
    if (
        user.role == UserRole.ADMIN
        and losing_admin
        and user_repository.count_active_admins(session, excluding_id=user.id) == 0
    ):
        raise ValidationFailedError(
            "This is the last active administrator",
            code=ErrorCode.USER_LAST_ADMIN,
        )

    if display_name is not None:
        user.display_name = display_name.strip()
    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active
        if not is_active:
            # Disabling must take effect now, not when the access token expires.
            user_repository.revoke_all_sessions(session, user.id)
            user.token_version += 1

    audit_service.record(
        session,
        action=AuditAction.USER_UPDATED,
        username=actor.username if actor else "",
        user_id=actor.id if actor else None,
        entity_type="user",
        entity_id=str(user.id),
        before=before,
        after={"display_name": user.display_name, "role": user.role, "is_active": user.is_active},
    )
    session.commit()
    return user


def change_own_password(
    session: Session, user: User, *, current_password: str, new_password: str
) -> None:
    if not verify_password(user.password_hash, current_password):
        raise AuthError(
            "Current password is incorrect", code=ErrorCode.AUTH_INVALID_CREDENTIALS
        )
    _validate_password(new_password)
    _apply_new_password(session, user, new_password, actor=user)


def reset_password(session: Session, user_id: int, *, new_password: str, actor: User) -> User:
    user = user_repository.get_by_id(session, user_id)
    if user is None:
        raise NotFoundError(f"No user with id {user_id}")
    _validate_password(new_password)
    _apply_new_password(session, user, new_password, actor=actor)
    return user


def _apply_new_password(session: Session, user: User, new_password: str, *, actor: User) -> None:
    user.password_hash = hash_password(new_password)
    # A password change must end every existing session. Otherwise a user who
    # changes their password precisely because someone else has it leaves that
    # someone signed in.
    user_repository.revoke_all_sessions(session, user.id)
    user.token_version += 1

    audit_service.record(
        session,
        action=AuditAction.PASSWORD_CHANGED,
        username=actor.username,
        user_id=actor.id,
        entity_type="user",
        entity_id=str(user.id),
    )
    session.commit()


def _validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationFailedError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
        )
