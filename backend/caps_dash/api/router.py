"""Aggregate API router.

Every feature router is included here, and the catch-all lives at the bottom.
Ordering matters: the catch-all must be registered after all real routes, and
the whole `/api` router must be mounted before the SPA static mount, or an
unknown `/api/...` path would return `index.html` with a 200.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..errors.codes import ErrorCode
from ..errors.exceptions import NotFoundError
from .routes.auth_routes import router as auth_router
from .routes.health_routes import router as health_router
from .routes.user_routes import router as user_router

api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(user_router)


@api_router.api_route(
    "/{unmatched:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
def api_not_found(unmatched: str) -> None:
    """Unknown API paths get an error envelope, never the SPA shell."""
    raise NotFoundError(
        f"No API route matches /api/{unmatched}",
        code=ErrorCode.NOT_FOUND,
    )
