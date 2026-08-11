"""Authentication endpoints.

Handlers are `def`, not `async def`: FastAPI runs sync handlers in a
threadpool, and the whole data layer is sync SQLAlchemy. Only the WebSocket
endpoints are async.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from ...db.models import User
from ...db.session import get_session
from ...db.types import utc_now
from ...errors.codes import ErrorCode
from ...errors.exceptions import AuthError, NotFoundError
from ...repositories import user_repository
from ...security.current_user import CurrentUser, get_current_user
from ...security.refresh_cookie import (
    clear_refresh_cookie,
    read_refresh_cookie,
    set_refresh_cookie,
)
from ...services import auth_service, user_service
from ..schemas.auth_schemas import (
    ChangePasswordRequest,
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    RefreshResponse,
    SessionResponse,
)
from ..schemas.common_schemas import OkResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "")


def _require_user(session: Session, current: CurrentUser) -> User:
    user = user_repository.get_by_id(session, current.id)
    if user is None:
        raise AuthError("Account no longer exists", code=ErrorCode.AUTH_INACTIVE_USER)
    return user


@router.post("/login", response_model=LoginResponse, summary="Sign in")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> LoginResponse:
    state = request.app.state.caps
    pair = auth_service.login(
        session,
        state.settings,
        state.services["login_limiter"],
        username=payload.username,
        password=payload.password,
        client_ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    set_refresh_cookie(response, state.settings, pair.refresh_token)
    return LoginResponse(
        access_token=pair.access_token,
        expires_in_s=state.settings.access_token_ttl_min * 60,
        user=CurrentUserResponse.model_validate(pair.user),
    )


@router.post("/refresh", response_model=RefreshResponse, summary="Exchange the refresh cookie")
def refresh(
    request: Request, response: Response, session: Session = Depends(get_session)
) -> RefreshResponse:
    state = request.app.state.caps
    token = read_refresh_cookie(request)
    if not token:
        raise AuthError("No refresh session", code=ErrorCode.AUTH_REQUIRED)

    pair = auth_service.refresh(
        session,
        state.settings,
        refresh_token=token,
        client_ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    set_refresh_cookie(response, state.settings, pair.refresh_token)
    return RefreshResponse(
        access_token=pair.access_token,
        expires_in_s=state.settings.access_token_ttl_min * 60,
    )


@router.post("/logout", response_model=OkResponse, summary="Sign out this device")
def logout(
    request: Request, response: Response, session: Session = Depends(get_session)
) -> OkResponse:
    state = request.app.state.caps
    auth_service.logout(session, state.settings, refresh_token=read_refresh_cookie(request))
    clear_refresh_cookie(response, state.settings)
    return OkResponse()


@router.post("/logout-all", response_model=OkResponse, summary="Sign out everywhere")
def logout_all(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    current: CurrentUser = Depends(get_current_user),
) -> OkResponse:
    auth_service.logout_everywhere(session, _require_user(session, current))
    clear_refresh_cookie(response, request.app.state.caps.settings)
    return OkResponse()


@router.get("/me", response_model=CurrentUserResponse, summary="The signed-in account")
def me(current: CurrentUser = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(
        username=current.username, display_name=current.display_name, role=current.role
    )


@router.post("/change-password", response_model=OkResponse, summary="Change my password")
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    request: Request,
    session: Session = Depends(get_session),
    current: CurrentUser = Depends(get_current_user),
) -> OkResponse:
    user_service.change_own_password(
        session,
        _require_user(session, current),
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    # Every session was just revoked, including this one. Clear the cookie so
    # the browser is not left holding a token that no longer works.
    clear_refresh_cookie(response, request.app.state.caps.settings)
    return OkResponse()


@router.get("/sessions", response_model=list[SessionResponse], summary="My active sessions")
def list_sessions(
    session: Session = Depends(get_session),
    current: CurrentUser = Depends(get_current_user),
) -> list[SessionResponse]:
    rows = user_repository.list_active_sessions(session, current.id)
    return [SessionResponse.model_validate(row) for row in rows]


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke one of my sessions",
)
def revoke_session(
    session_id: int,
    session: Session = Depends(get_session),
    current: CurrentUser = Depends(get_current_user),
) -> None:
    rows = user_repository.list_active_sessions(session, current.id)
    target = next((row for row in rows if row.id == session_id), None)
    if target is None:
        # Only ever their own sessions: looking it up within the caller's list
        # means another user's id cannot be probed or revoked from here.
        raise NotFoundError(f"No active session with id {session_id}")
    target.revoked_at = utc_now()
    session.commit()
