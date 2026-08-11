"""Slot listing, detail and metadata updates.

Polygons are read-only here (`SlotDetailResponse.polygon`) and never written -
`PATCH` only ever changes `code`, `floor`, `is_active`. See
`slot_service.update_slot` for why geometry has a separate write path.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...db.enums import UserRole
from ...db.models import User
from ...db.session import get_session
from ...errors.codes import ErrorCode
from ...errors.exceptions import AuthError
from ...repositories import user_repository
from ...security.current_user import CurrentUser
from ...security.rbac import require_role
from ...services import slot_service
from ..deps import ServiceContext, get_service_context
from ..pagination import PageParams, page_params
from ..schemas.common_schemas import Page
from ..schemas.slot_schemas import SlotDetailResponse, SlotResponse, UpdateSlotRequest

router = APIRouter(prefix="/slots", tags=["Slots"])

SecurityOrAbove = Depends(require_role(UserRole.SECURITY))
AdminOnly = Depends(require_role(UserRole.ADMIN))


def _actor(session: Session, current: CurrentUser) -> User:
    """Load the acting account for the audit row. Mirrors `user_routes._actor`."""
    user = user_repository.get_by_id(session, current.id)
    if user is None:
        raise AuthError("Account no longer exists", code=ErrorCode.AUTH_INACTIVE_USER)
    return user


@router.get("", response_model=Page[SlotResponse], summary="List slots")
def list_slots(
    floor: str | None = Query(default=None),
    camera_id: int | None = Query(default=None),
    state: str | None = Query(default=None),
    params: PageParams = Depends(page_params),
    session: Session = Depends(get_session),
    _: CurrentUser = SecurityOrAbove,
) -> Page[SlotResponse]:
    slots, total = slot_service.list_slots(
        session, floor=floor, camera_id=camera_id, state=state, params=params
    )
    return Page[SlotResponse](
        items=[SlotResponse.model_validate(slot) for slot in slots],
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


@router.get("/{slot_id}", response_model=SlotDetailResponse, summary="Slot detail")
def get_slot(
    slot_id: int, session: Session = Depends(get_session), _: CurrentUser = SecurityOrAbove
) -> SlotDetailResponse:
    slot = slot_service.get_slot(session, slot_id)
    return SlotDetailResponse.model_validate(slot)


@router.patch("/{slot_id}", response_model=SlotDetailResponse, summary="Update slot metadata")
def update_slot(
    slot_id: int,
    payload: UpdateSlotRequest,
    session: Session = Depends(get_session),
    current: CurrentUser = AdminOnly,
    ctx: ServiceContext = Depends(get_service_context),
) -> SlotDetailResponse:
    slot = slot_service.update_slot(
        session,
        slot_id,
        code=payload.code,
        floor=payload.floor,
        is_active=payload.is_active,
        actor=_actor(session, current),
        ctx=ctx,
    )
    return SlotDetailResponse.model_validate(slot)
