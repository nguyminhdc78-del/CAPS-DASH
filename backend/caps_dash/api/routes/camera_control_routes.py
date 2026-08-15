"""Reading and changing a camera's sensor settings.

`async def`, like `camera_diagnostics_routes` and for the same reason: these
two endpoints are pure network I/O to the device, doing no ORM work beyond
loading the row that names its address. That exception to the sync-handler
rule is documented in `docs/code-standards.md`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...config.settings import Settings
from ...db.enums import UserRole
from ...db.session import get_session
from ...repositories import camera_repository
from ...security.current_user import CurrentUser
from ...security.rbac import require_role
from ...services import camera_control_service, slot_led_service
from ..deps import ServiceContext, get_service_context, get_settings_dep
from ..schemas.camera_schemas import (
    CameraSettingsResponse,
    RingTestRequest,
    RingTestResponse,
    UpdateCameraSettingsRequest,
)

router = APIRouter(prefix="/cameras", tags=["Cameras"])

AdminOnly = Depends(require_role(UserRole.ADMIN))
SecurityOrAbove = Depends(require_role(UserRole.SECURITY))


@router.get(
    "/{camera_id}/settings",
    response_model=CameraSettingsResponse,
    summary="Read the camera's current sensor settings",
)
async def read_settings(
    camera_id: int,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
    _: CurrentUser = SecurityOrAbove,
) -> CameraSettingsResponse:
    camera = camera_repository.get_or_raise(session, camera_id)
    reported = await camera_control_service.read_settings(camera, settings)
    return CameraSettingsResponse(camera_id=camera_id, settings=reported.values)


@router.patch(
    "/{camera_id}/settings",
    response_model=CameraSettingsResponse,
    summary="Change sensor settings (brightness, exposure lock, ...)",
)
async def update_settings(
    camera_id: int,
    payload: UpdateCameraSettingsRequest,
    session: Session = Depends(get_session),
    current: CurrentUser = AdminOnly,
    ctx: ServiceContext = Depends(get_service_context),
) -> CameraSettingsResponse:
    camera = camera_repository.get_or_raise(session, camera_id)

    applied = await camera_control_service.update(
        session, camera=camera, changes=payload.to_changes(), actor=current, ctx=ctx
    )
    # Read back rather than echoing the request: the sensor clamps some values
    # silently, so what it reports is the truth and what was asked for is not.
    reported = await camera_control_service.read_settings(camera, ctx.settings)

    return CameraSettingsResponse(
        camera_id=camera_id, settings=reported.values, applied=applied
    )


@router.post(
    "/{camera_id}/ring-test",
    response_model=RingTestResponse,
    summary="Light a pattern on the camera node's LED ring, for commissioning",
)
async def test_ring(
    camera_id: int,
    payload: RingTestRequest,
    session: Session = Depends(get_session),
    _: CurrentUser = AdminOnly,
) -> RingTestResponse:
    """Prove the ring is wired and shows the colour it is meant to.

    Not audited, unlike a settings change: this writes nothing, the camera
    loop takes the ring back within seconds, and the only lasting trace of a
    click would be an audit table full of people checking a lamp.
    """
    camera = camera_repository.get_or_raise(session, camera_id)
    await slot_led_service.push_test_pattern(
        source_type=camera.source_type,
        source_url=camera.source_url,
        code=camera.code,
        slots=payload.slots,
    )
    return RingTestResponse(
        camera_id=camera_id,
        slots=payload.slots,
        reverts_within_s=slot_led_service.REFRESH_S,
    )
