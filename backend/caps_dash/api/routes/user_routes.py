"""User administration endpoints. Admin only."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from ...db.enums import UserRole
from ...db.models import User
from ...db.session import get_session
from ...errors.codes import ErrorCode
from ...errors.exceptions import AuthError, NotFoundError
from ...repositories import user_repository
from ...security.current_user import CurrentUser
from ...security.rbac import require_role
from ...services import auth_service, user_service
from ..schemas.common_schemas import OkResponse
from ..schemas.user_schemas import (
    CreateUserRequest,
    ResetPasswordRequest,
    UpdateUserRequest,
    UserResponse,
)

router = APIRouter(prefix="/users", tags=["Users"])

# One dependency on the router would be tidier, but naming it per route keeps
# the required role visible where someone reads the endpoint.
AdminOnly = Depends(require_role(UserRole.ADMIN))


def _actor(session: Session, current: CurrentUser) -> User:
    user = user_repository.get_by_id(session, current.id)
    if user is None:
        raise AuthError("Account no longer exists", code=ErrorCode.AUTH_INACTIVE_USER)
    return user


@router.get("", response_model=list[UserResponse], summary="List accounts")
def list_users(
    session: Session = Depends(get_session), _: CurrentUser = AdminOnly
) -> list[UserResponse]:
    return [UserResponse.model_validate(user) for user in user_repository.list_users(session)]


@router.post(
    "", response_model=UserResponse, status_code=status.HTTP_201_CREATED, summary="Create account"
)
def create_user(
    payload: CreateUserRequest,
    session: Session = Depends(get_session),
    current: CurrentUser = AdminOnly,
) -> UserResponse:
    user = user_service.create_user(
        session,
        username=payload.username,
        password=payload.password,
        display_name=payload.display_name,
        role=payload.role,
        actor=_actor(session, current),
    )
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse, summary="Update account")
def update_user(
    user_id: int,
    payload: UpdateUserRequest,
    session: Session = Depends(get_session),
    current: CurrentUser = AdminOnly,
) -> UserResponse:
    user = user_service.update_user(
        session,
        user_id,
        display_name=payload.display_name,
        role=payload.role,
        is_active=payload.is_active,
        actor=_actor(session, current),
    )
    return UserResponse.model_validate(user)


@router.post("/{user_id}/reset-password", response_model=OkResponse, summary="Reset a password")
def reset_password(
    user_id: int,
    payload: ResetPasswordRequest,
    session: Session = Depends(get_session),
    current: CurrentUser = AdminOnly,
) -> OkResponse:
    user_service.reset_password(
        session, user_id, new_password=payload.new_password, actor=_actor(session, current)
    )
    return OkResponse()


@router.post("/{user_id}/revoke-sessions", response_model=OkResponse, summary="Sign a user out")
def revoke_sessions(
    user_id: int,
    request: Request,
    session: Session = Depends(get_session),
    _: CurrentUser = AdminOnly,
) -> OkResponse:
    del request
    user = user_repository.get_by_id(session, user_id)
    if user is None:
        raise NotFoundError(f"No user with id {user_id}")
    auth_service.logout_everywhere(session, user)
    return OkResponse()
