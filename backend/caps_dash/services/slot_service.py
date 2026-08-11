"""Slot business rules: filtered listing, single lookup, metadata updates.

Polygons are not editable here. Geometry changes exclusively through
`PUT /cameras/{id}/slot-map` (owned by the camera slot-map service) so the ROI
editor has exactly one atomic write path for a polygon together with the
`src_frame_width/height` it was drawn against - a second write path through
this service could desync the two.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..api.pagination import PageParams, apply_page, count_rows
from ..db.enums import AuditAction
from ..db.models import ParkingSlot, User
from ..errors.codes import ErrorCode
from ..errors.exceptions import ConflictError
from ..repositories import slot_repository
from . import audit_service
from .service_context import ServiceContext


def list_slots(
    session: Session,
    *,
    floor: str | None,
    camera_id: int | None,
    state: str | None,
    params: PageParams,
) -> tuple[list[ParkingSlot], int]:
    """Filtered page of slots plus the unfiltered-by-page total."""
    query = slot_repository.list_query(floor=floor, camera_id=camera_id, state=state)
    total = count_rows(session, query)
    rows = session.execute(apply_page(query, params)).scalars().all()
    return list(rows), total


def get_slot(session: Session, slot_id: int) -> ParkingSlot:
    return slot_repository.get_or_raise(session, slot_id)


def _snapshot(slot: ParkingSlot) -> dict[str, object]:
    return {"code": slot.code, "floor": slot.floor, "is_active": slot.is_active}


def update_slot(
    session: Session,
    slot_id: int,
    *,
    code: str | None,
    floor: str | None,
    is_active: bool | None,
    actor: User,
    ctx: ServiceContext,
) -> ParkingSlot:
    """Rename / move floor / activate a slot. Never touches the polygon."""
    slot = slot_repository.get_or_raise(session, slot_id)
    before = _snapshot(slot)

    if code is not None and code != slot.code:
        clash = slot_repository.get_by_camera_and_code(
            session, slot.camera_id, code, exclude_id=slot.id
        )
        if clash is not None:
            raise ConflictError(
                f"Slot code {code!r} is already used on this camera",
                code=ErrorCode.SLOT_CODE_TAKEN,
            )
        slot.code = code
    if floor is not None:
        slot.floor = floor
    if is_active is not None:
        slot.is_active = is_active
    session.flush()

    audit_service.record(
        session,
        action=AuditAction.SLOT_MAP_UPDATED,
        username=actor.username,
        user_id=actor.id,
        entity_type="slot",
        entity_id=str(slot.id),
        before=before,
        after=_snapshot(slot),
    )
    session.commit()
    # AFTER commit: the running camera loop must reload the committed row, not
    # the pre-commit one - reloading first would look like the save silently
    # failing (deactivated/renamed slots keep matching the stale polygon set).
    ctx.request_reload(slot.camera_id)
    return slot
