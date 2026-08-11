"""Connection test and live snapshot - the two endpoints that reach outside
the process instead of only the database.

Both handlers below are `async def`. This is the ONE sanctioned exception to
the phase-07 sync-route rule: they do pure async network I/O (build a
throwaway `FrameSource`, read once off-thread with a hard timeout, close it)
and touch the ORM only for a single already-loaded read - no query beyond
that, no mutation, no audit row, no commit. Every other route in this phase
stays `def`.

Route-ordering note: `/cameras/test-connection` (2 path segments) and
`/cameras/{camera_id}/test-connection` (3 segments) cannot collide at the
routing layer regardless of which router `api/router.py` includes first -
their path templates differ in depth, so Starlette can never match one
request against both. `camera_id` is still kept a plain `int` (not a
Starlette `{camera_id:int}` path converter): a non-numeric segment there 422s
via pydantic request validation rather than silently matching a nearby route,
which is enough safety without depending on include order.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ...db.enums import CameraSourceType, UserRole
from ...repositories import camera_repository
from ...security.current_user import CurrentUser
from ...security.rbac import require_role
from ...services import camera_diagnostics_service
from ..deps import ServiceContext, get_service_context, get_session
from ..schemas.camera_schemas import ConnectionTestRequest, ConnectionTestResponse

router = APIRouter(prefix="/cameras", tags=["Cameras"])

AdminOnly = Depends(require_role(UserRole.ADMIN))


@router.post(
    "/test-connection",
    response_model=ConnectionTestResponse,
    summary="Test an unsaved camera draft",
)
async def test_connection_draft(
    payload: ConnectionTestRequest,
    ctx: ServiceContext = Depends(get_service_context),
    _: CurrentUser = AdminOnly,
) -> ConnectionTestResponse:
    result = await camera_diagnostics_service.test_connection(
        camera_id=0,
        code="draft",
        source_type=payload.source_type,
        source_url=payload.source_url,
        settings=ctx.settings,
    )
    return _to_response(result)


@router.post(
    "/{camera_id}/test-connection",
    response_model=ConnectionTestResponse,
    summary="Test a saved camera",
)
async def test_connection_saved(
    camera_id: int,
    session: Session = Depends(get_session),
    ctx: ServiceContext = Depends(get_service_context),
    _: CurrentUser = AdminOnly,
) -> ConnectionTestResponse:
    camera = camera_repository.get_or_raise(session, camera_id)
    result = await camera_diagnostics_service.test_connection(
        camera_id=camera.id,
        code=camera.code,
        source_type=CameraSourceType(camera.source_type),
        source_url=camera.source_url,
        settings=ctx.settings,
    )
    return _to_response(result)


@router.get(
    "/{camera_id}/snapshot",
    response_class=Response,
    summary="Latest JPEG still, for the ROI editor",
)
async def get_snapshot(
    camera_id: int,
    session: Session = Depends(get_session),
    ctx: ServiceContext = Depends(get_service_context),
    _: CurrentUser = AdminOnly,
) -> Response:
    camera = camera_repository.get_or_raise(session, camera_id)
    jpeg = await camera_diagnostics_service.get_snapshot(camera=camera, ctx=ctx)
    return Response(content=jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


def _to_response(
    result: camera_diagnostics_service.ConnectionProbeResult,
) -> ConnectionTestResponse:
    return ConnectionTestResponse(
        ok=result.ok,
        latency_ms=result.latency_ms,
        frame_width=result.frame_width,
        frame_height=result.frame_height,
        error=result.error,
        error_code=result.error_code,
    )
