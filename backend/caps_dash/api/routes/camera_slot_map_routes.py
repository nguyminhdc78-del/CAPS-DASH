"""Bulk polygon replace for one camera's slot map, and the read the ROI editor
uses to load it.

Split out of `camera_routes.py` to keep that module under the 200-line cap -
see its docstring.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...db.enums import UserRole
from ...security.current_user import CurrentUser
from ...security.rbac import require_role
from ...services import slot_map_service
from ..deps import ServiceContext, get_service_context, get_session
from ..schemas.camera_schemas import SlotMapRequest, SlotMapResponse

router = APIRouter(prefix="/cameras", tags=["Cameras"])

SecurityOnly = Depends(require_role(UserRole.SECURITY))
AdminOnly = Depends(require_role(UserRole.ADMIN))


@router.get(
    "/{camera_id}/slot-map", response_model=SlotMapResponse, summary="Current slot map"
)
def get_slot_map(
    camera_id: int,
    session: Session = Depends(get_session),
    _: CurrentUser = SecurityOnly,
) -> SlotMapResponse:
    return slot_map_service.get_map(session, camera_id)


@router.put(
    "/{camera_id}/slot-map",
    response_model=SlotMapResponse,
    summary="Atomic bulk replace of the slot map",
)
def replace_slot_map(
    camera_id: int,
    payload: SlotMapRequest,
    session: Session = Depends(get_session),
    ctx: ServiceContext = Depends(get_service_context),
    current: CurrentUser = AdminOnly,
) -> SlotMapResponse:
    return slot_map_service.replace(
        session, actor=current, camera_id=camera_id, payload=payload, ctx=ctx
    )
