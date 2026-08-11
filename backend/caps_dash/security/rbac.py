"""Role-based access control.

Ranked comparison, never equality. An admin must be able to do everything a
guard can without every route listing both roles - and the moment routes start
enumerating roles, one of them gets forgotten when a role is added.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends

from ..db.enums import UserRole
from ..errors.codes import ErrorCode
from ..errors.exceptions import ForbiddenError
from .current_user import CurrentUser, get_current_user

ROLE_RANK: dict[str, int] = {
    UserRole.RESIDENT: 1,
    UserRole.SECURITY: 2,
    UserRole.ADMIN: 3,
}


def rank_of(role: str) -> int:
    """Unknown roles rank 0 - they can reach nothing."""
    return ROLE_RANK.get(role, 0)


def has_at_least(role: str, minimum: UserRole) -> bool:
    return rank_of(role) >= ROLE_RANK[minimum]


def assert_role(user: CurrentUser, minimum: UserRole) -> None:
    """Plain function so services and the WebSocket layer can reuse the check.

    The WebSocket endpoint authenticates via a message after connect rather
    than a header, so it cannot use the FastAPI dependency - but it must apply
    exactly the same rule.
    """
    if not has_at_least(user.role, minimum):
        raise ForbiddenError(
            "This account does not have permission for that", code=ErrorCode.FORBIDDEN
        )


def require_role(minimum: UserRole) -> Callable[..., CurrentUser]:
    """Dependency factory: `Depends(require_role(UserRole.SECURITY))`."""

    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        assert_role(user, minimum)
        return user

    return dependency
