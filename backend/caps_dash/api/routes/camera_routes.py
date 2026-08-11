"""Camera CRUD, paginated list-with-health, and live confidence tuning.

Slot-map replace/read and connection-test/snapshot live in
`camera_slot_map_routes.py` / `camera_diagnostics_routes.py` instead of here,
so this module stays under the 200-line cap - one combined module was tried
first and blew well past it once every verb got a docstring.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ...db.enums import UserRole
from ...security.current_user import CurrentUser
from ...security.rbac import require_role
from ...services import camera_service
from ..deps import ServiceContext, get_service_context, get_session
from ..pagination import PageParams, page_params
from ..schemas.camera_schemas import (
    CameraResponse,
    CameraWithHealth,
    CreateCameraRequest,
    RuntimeTuningRequest,
    UpdateCameraRequest,
)
from ..schemas.common_schemas import OkResponse, Page

router = APIRouter(prefix="/cameras", tags=["Cameras"])

SecurityOnly = Depends(require_role(UserRole.SECURITY))
AdminOnly = Depends(require_role(UserRole.ADMIN))


@router.get("", response_model=Page[CameraWithHealth], summary="List cameras with live health")
def list_cameras(
    session: Session = Depends(get_session),
    ctx: ServiceContext = Depends(get_service_context),
    params: PageParams = Depends(page_params),
    _: CurrentUser = SecurityOnly,
) -> Page[CameraWithHealth]:
    items, total = camera_service.list_cameras(session, ctx, params)
    return Page(items=items, total=total, limit=params.limit, offset=params.offset)


@router.post(
    "",
    response_model=CameraResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a camera",
)
def create_camera(
    payload: CreateCameraRequest,
    session: Session = Depends(get_session),
    ctx: ServiceContext = Depends(get_service_context),
    current: CurrentUser = AdminOnly,
) -> CameraResponse:
    camera = camera_service.create_camera(session, actor=current, payload=payload, ctx=ctx)
    return CameraResponse.model_validate(camera)


@router.get(
    "/{camera_id}", response_model=CameraWithHealth, summary="Get one camera with live health"
)
def get_camera(
    camera_id: int,
    session: Session = Depends(get_session),
    ctx: ServiceContext = Depends(get_service_context),
    _: CurrentUser = SecurityOnly,
) -> CameraWithHealth:
    return camera_service.get_camera(session, camera_id, ctx)


@router.patch("/{camera_id}", response_model=CameraResponse, summary="Update a camera")
def update_camera(
    camera_id: int,
    payload: UpdateCameraRequest,
    session: Session = Depends(get_session),
    ctx: ServiceContext = Depends(get_service_context),
    current: CurrentUser = AdminOnly,
) -> CameraResponse:
    camera = camera_service.update_camera(
        session, actor=current, camera_id=camera_id, payload=payload, ctx=ctx
    )
    return CameraResponse.model_validate(camera)


@router.delete("/{camera_id}", response_model=OkResponse, summary="Delete a camera and its slots")
def delete_camera(
    camera_id: int,
    session: Session = Depends(get_session),
    ctx: ServiceContext = Depends(get_service_context),
    current: CurrentUser = AdminOnly,
) -> OkResponse:
    camera_service.delete_camera(session, actor=current, camera_id=camera_id, ctx=ctx)
    return OkResponse()


@router.patch(
    "/{camera_id}/runtime",
    response_model=CameraResponse,
    summary="Live confidence tuning - no restart",
)
def update_runtime(
    camera_id: int,
    payload: RuntimeTuningRequest,
    session: Session = Depends(get_session),
    ctx: ServiceContext = Depends(get_service_context),
    current: CurrentUser = SecurityOnly,
) -> CameraResponse:
    camera = camera_service.update_runtime(
        session, actor=current, camera_id=camera_id, payload=payload, ctx=ctx
    )
    return CameraResponse.model_validate(camera)
