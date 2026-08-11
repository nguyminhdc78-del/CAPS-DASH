"""Resolving the caller's identity from a bearer token."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config.settings import Settings
from ..db.models import User
from ..db.session import get_session
from ..errors.codes import ErrorCode
from ..errors.exceptions import AuthError
from .jwt_tokens import decode_token

# auto_error=False so a missing header produces our own envelope rather than
# FastAPI's bare {"detail": ...}, which the frontend cannot localise.
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: int
    username: str
    role: str
    display_name: str = ""


def resolve_user_from_token(
    session: Session, settings: Settings, token: str
) -> CurrentUser:
    """Verify an access token and load the account behind it.

    Shared with the WebSocket layer, which authenticates via a message after
    connect (browsers cannot set headers on a WebSocket handshake) and so
    cannot use the HTTP dependency below.
    """
    claims = decode_token(settings, token, expected_type="access")

    user = session.execute(
        select(User).where(User.username == claims.subject)
    ).scalar_one_or_none()

    if user is None or not user.is_active:
        # Same code either way: whether the account was deleted or merely
        # disabled is not the caller's business.
        raise AuthError("Account is not active", code=ErrorCode.AUTH_INACTIVE_USER)

    if user.token_version != claims.token_version:
        # The global kill-switch fired: password changed, account disabled and
        # re-enabled, or an admin revoked everything.
        raise AuthError("Session was revoked", code=ErrorCode.AUTH_SESSION_REVOKED)

    return CurrentUser(
        id=user.id, username=user.username, role=user.role, display_name=user.display_name
    )


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> CurrentUser:
    if credentials is None:
        raise AuthError("Authentication required", code=ErrorCode.AUTH_REQUIRED)
    settings = request.app.state.caps.settings
    return resolve_user_from_token(session, settings, credentials.credentials)


def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> CurrentUser | None:
    """For endpoints that behave differently when signed in but do not require it."""
    if credentials is None:
        return None
    try:
        settings = request.app.state.caps.settings
        return resolve_user_from_token(session, settings, credentials.credentials)
    except AuthError:
        return None
