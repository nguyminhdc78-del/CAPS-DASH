"""Login, refresh rotation, and logout."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

from sqlalchemy.orm import Session

from ..config.settings import Settings
from ..db.enums import AuditAction
from ..db.models import RefreshSession, User
from ..db.types import utc_now
from ..errors.codes import ErrorCode
from ..errors.exceptions import AuthError
from ..observability.logging_setup import get_logger
from ..repositories import user_repository
from ..security.jwt_tokens import decode_token, encode_access, encode_refresh
from ..security.password_hasher import (
    consume_dummy_verification,
    hash_password,
    needs_rehash,
    verify_password,
)
from ..security.rate_limiter import SlidingWindowLimiter, ip_key, user_key
from . import audit_service

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    user: User


def login(
    session: Session,
    settings: Settings,
    limiter: SlidingWindowLimiter,
    *,
    username: str,
    password: str,
    client_ip: str = "",
    user_agent: str = "",
) -> TokenPair:
    keys = [user_key(username), ip_key(client_ip)] if client_ip else [user_key(username)]
    for key in keys:
        limiter.check(key)

    user = user_repository.get_by_username(session, username)

    if user is None:
        # Burn the same CPU a real verification costs. Returning early here
        # makes "no such user" measurably faster than "wrong password", and
        # that difference is enough to enumerate valid accounts.
        consume_dummy_verification(password)
        _fail_login(limiter, keys)

    if not user.is_active or not verify_password(user.password_hash, password):
        _fail_login(limiter, keys)

    # Opportunistically upgrade a hash left over from weaker parameters.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    for key in keys:
        limiter.reset(key)

    user.last_login_at = utc_now()
    pair = _issue_pair(session, settings, user, client_ip=client_ip, user_agent=user_agent)

    audit_service.record(
        session,
        action=AuditAction.LOGIN,
        username=user.username,
        user_id=user.id,
        entity_type="user",
        entity_id=str(user.id),
        client_ip=client_ip,
    )
    session.commit()
    return pair


def _fail_login(limiter: SlidingWindowLimiter, keys: list[str]) -> NoReturn:
    """One message for every failure mode.

    Saying which of the username or the password was wrong hands an attacker
    a free account-enumeration oracle.
    """
    for key in keys:
        limiter.record(key)
    raise AuthError(
        "Incorrect username or password", code=ErrorCode.AUTH_INVALID_CREDENTIALS
    )


def refresh(
    session: Session,
    settings: Settings,
    *,
    refresh_token: str,
    client_ip: str = "",
    user_agent: str = "",
) -> TokenPair:
    """Rotate a refresh token, or detect that it has been replayed."""
    claims = decode_token(settings, refresh_token, expected_type="refresh")
    stored = user_repository.get_session_by_jti(session, claims.jti)

    if stored is None:
        raise AuthError("Session not recognised", code=ErrorCode.AUTH_TOKEN_INVALID)

    if not stored.is_usable():
        # This token was already rotated, revoked, or has expired. A rotated
        # one being presented again means two parties hold it: the legitimate
        # user and somebody else. There is no way to tell which is which, so
        # close every session and make them all sign in again.
        revoked = user_repository.revoke_all_sessions(session, stored.user_id)
        audit_service.record(
            session,
            action=AuditAction.SESSION_REVOKED,
            username=stored.user.username,
            user_id=stored.user_id,
            entity_type="refresh_session",
            entity_id=str(stored.id),
            after={"reason": "refresh token replay", "sessions_revoked": revoked},
            client_ip=client_ip,
        )
        session.commit()
        logger.warning(
            "refresh_token_replay", user_id=stored.user_id, sessions_revoked=revoked
        )
        raise AuthError(
            "Session replay detected; all sessions were revoked",
            code=ErrorCode.AUTH_SESSION_REUSED,
        )

    user = stored.user
    if not user.is_active:
        raise AuthError("Account is not active", code=ErrorCode.AUTH_INACTIVE_USER)
    if user.token_version != claims.token_version:
        raise AuthError("Session was revoked", code=ErrorCode.AUTH_SESSION_REVOKED)

    now = utc_now()
    stored.rotated_at = now
    stored.last_used_at = now

    pair = _issue_pair(session, settings, user, client_ip=client_ip, user_agent=user_agent)
    session.commit()
    return pair


def logout(session: Session, settings: Settings, *, refresh_token: str | None) -> None:
    """Close the session this cookie names. Missing or bad cookie is not an error.

    The user asked to be logged out; refusing because their token was already
    invalid would leave them staring at a failure for something that has, in
    effect, already happened.
    """
    if not refresh_token:
        return
    try:
        claims = decode_token(settings, refresh_token, expected_type="refresh")
    except AuthError:
        return

    stored = user_repository.get_session_by_jti(session, claims.jti)
    if stored is None or stored.revoked_at is not None:
        return

    stored.revoked_at = utc_now()
    audit_service.record(
        session,
        action=AuditAction.LOGOUT,
        username=stored.user.username,
        user_id=stored.user_id,
        entity_type="refresh_session",
        entity_id=str(stored.id),
    )
    session.commit()


def logout_everywhere(session: Session, user: User) -> int:
    """Revoke every session and invalidate outstanding access tokens."""
    count = user_repository.revoke_all_sessions(session, user.id)
    # Access tokens are stateless, so revoking sessions alone would leave them
    # valid until they expire. Bumping the version is what actually stops them.
    user.token_version += 1
    audit_service.record(
        session,
        action=AuditAction.SESSION_REVOKED,
        username=user.username,
        user_id=user.id,
        entity_type="user",
        entity_id=str(user.id),
        after={"sessions_revoked": count, "reason": "logout everywhere"},
    )
    session.commit()
    return count


def _issue_pair(
    session: Session,
    settings: Settings,
    user: User,
    *,
    client_ip: str,
    user_agent: str,
) -> TokenPair:
    access = encode_access(
        settings, username=user.username, role=user.role, token_version=user.token_version
    )
    refresh_token, jti, expires_at = encode_refresh(
        settings, username=user.username, token_version=user.token_version
    )
    session.add(
        RefreshSession(
            user_id=user.id,
            jti=jti,
            expires_at=expires_at,
            user_agent=user_agent[:255],
            client_ip=client_ip[:64],
        )
    )
    return TokenPair(access_token=access, refresh_token=refresh_token, user=user)
