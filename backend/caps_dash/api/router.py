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
from .routes.alert_routes import router as alert_router
from .routes.audit_routes import router as audit_router
from .routes.auth_routes import router as auth_router
from .routes.camera_control_routes import router as camera_control_router
from .routes.camera_diagnostics_routes import router as camera_diagnostics_router
from .routes.camera_routes import router as camera_router
from .routes.camera_slot_map_routes import router as camera_slot_map_router
from .routes.health_routes import router as health_router
from .routes.history_routes import router as history_router
from .routes.slot_routes import router as slot_router
from .routes.stats_routes import router as stats_router
from .routes.summary_routes import router as summary_router
from .routes.system_routes import router as system_router
from .routes.user_routes import router as user_router
from .schemas.common_schemas import ERROR_RESPONSES

api_router = APIRouter(responses=ERROR_RESPONSES)

api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(summary_router)
api_router.include_router(slot_router)
# Diagnostics first: it owns the literal `/cameras/test-connection`, and a
# `/cameras/{camera_id}` route registered ahead of it would claim that path
# and answer 422 instead.
api_router.include_router(camera_diagnostics_router)
api_router.include_router(camera_control_router)
api_router.include_router(camera_slot_map_router)
api_router.include_router(camera_router)
api_router.include_router(history_router)
api_router.include_router(stats_router)
api_router.include_router(alert_router)
api_router.include_router(audit_router)
api_router.include_router(system_router)


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
