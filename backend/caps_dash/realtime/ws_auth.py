"""The post-connect authentication handshake.

**The token is never in the URL.** A `?token=` query string lands in uvicorn's
access log, in every proxy log between the browser and the board, and in
browser history - three places a bearer credential must not be. Browsers cannot
set headers on a WebSocket handshake either, so the credential arrives as the
first message after accept, under a deadline, and nothing is sent back until it
checks out.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
from dataclasses import dataclass

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session, sessionmaker

from ..config.settings import Settings
from ..db.enums import UserRole
from ..db.session import session_scope
from ..errors.exceptions import AppError
from ..observability.logging_setup import get_logger
from ..security.current_user import CurrentUser, resolve_user_from_token
from ..security.jwt_tokens import decode_token
from ..security.rbac import assert_role
from . import close_codes

logger = get_logger(__name__)

# An auth message is a few hundred bytes. Anything larger is hostile or broken,
# and must be rejected before it is parsed.
MAX_AUTH_MESSAGE_BYTES = 4096


@dataclass(frozen=True, slots=True)
class AuthenticatedViewer:
    """Who is watching, and when their credential stops being valid."""

    user: CurrentUser
    expires_at: dt.datetime | None


async def authenticate_connection(
    websocket: WebSocket,
    settings: Settings,
    session_factory: sessionmaker[Session],
) -> AuthenticatedViewer | None:
    """Accept, wait for `{"type":"auth","token":...}`, verify, check the role.

    Returns None after closing the socket itself, so the caller only has to
    check for None rather than duplicate the close handling.
    """
    await websocket.accept()

    try:
        raw = await asyncio.wait_for(
            websocket.receive_text(), timeout=settings.ws_auth_deadline_s
        )
    except (TimeoutError, WebSocketDisconnect, RuntimeError):
        # A client that connects and says nothing is either broken or probing.
        # Either way it holds a connection slot, so it goes promptly.
        await _close(websocket, close_codes.REASON_AUTH_TIMEOUT)
        return None

    token = _extract_token(raw)
    if token is None:
        await _close(websocket, close_codes.REASON_AUTH_INVALID)
        return None

    try:
        # Blocking ORM work, so it goes to a thread rather than stalling the
        # event loop that every other camera's fan-out runs on.
        viewer = await asyncio.to_thread(
            _resolve_viewer, session_factory, settings, token
        )
    except AppError as exc:
        logger.info("ws_auth_rejected", code=str(exc.code))
        await _close(websocket, _reason_for(exc))
        return None

    return viewer


def _resolve_viewer(
    session_factory: sessionmaker[Session], settings: Settings, token: str
) -> AuthenticatedViewer:
    """Verify the token, load the account, and apply the same role rule as REST.

    Residents never reach camera imagery. The check is server-side and per
    connection - a client that hides the live view in its own UI is not a
    control.
    """
    claims = decode_token(settings, token, expected_type="access")
    with session_scope(session_factory) as session:
        user = resolve_user_from_token(session, settings, token)
    assert_role(user, UserRole.SECURITY)
    return AuthenticatedViewer(user=user, expires_at=claims.expires_at)


def _extract_token(raw: str) -> str | None:
    """Parse the handshake message. All client input is treated as hostile."""
    if len(raw) > MAX_AUTH_MESSAGE_BYTES:
        return None
    try:
        message = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(message, dict) or message.get("type") != "auth":
        return None
    token = message.get("token")
    return token if isinstance(token, str) and token else None


def _reason_for(exc: AppError) -> str:
    if exc.status_code == 403:
        return close_codes.REASON_FORBIDDEN
    if str(exc.code).endswith("TOKEN_EXPIRED"):
        return close_codes.REASON_TOKEN_EXPIRED
    return close_codes.REASON_AUTH_INVALID


async def _close(websocket: WebSocket, reason: str) -> None:
    """Close with 1008 and a machine-readable reason.

    Never raises: by the time we reject a connection the client has often
    already hung up, and there is nothing left to report about a socket that
    is closing anyway.
    """
    with contextlib.suppress(RuntimeError, WebSocketDisconnect):
        await websocket.close(code=close_codes.POLICY_VIOLATION, reason=reason)
