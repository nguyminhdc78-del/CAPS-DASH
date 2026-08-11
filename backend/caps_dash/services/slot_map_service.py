"""Atomic bulk replace of a camera's slot map.

UPSERT BY CODE, never delete-and-reinsert every slot. A `parking_slots` row is
the parent of `slot_state_history` (`ON DELETE CASCADE`); reinserting a fresh
row for a code that already exists would hand it a new id and, through that
same cascade, silently orphan-delete every history row the old id owned. So:
codes already present are updated IN PLACE (same id, same history), codes new
to the request are inserted, and a code that disappears is removed ONLY when
the caller sets `allow_delete=true` - otherwise the whole replace is refused
and the codes that would have been lost are named in the error, so the editor
can show the installer exactly what "confirm delete" means before they click it.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from ..api.schemas.camera_schemas import SlotMapEntry, SlotMapRequest, SlotMapResponse
from ..api.schemas.polygon_schemas import PolygonModel
from ..db.enums import AuditAction
from ..db.models import ParkingSlot
from ..errors.codes import ErrorCode
from ..errors.exceptions import ConflictError, ValidationFailedError
from ..repositories import camera_repository
from ..security.current_user import CurrentUser
from . import audit_service
from .service_context import ServiceContext


def get_map(session: Session, camera_id: int) -> SlotMapResponse:
    camera_repository.get_or_raise(session, camera_id)  # 404s a bad id early
    slots = camera_repository.list_slots(session, camera_id)
    return _to_response(camera_id, slots)


def replace(
    session: Session,
    *,
    actor: CurrentUser,
    camera_id: int,
    payload: SlotMapRequest,
    ctx: ServiceContext,
) -> SlotMapResponse:
    camera_repository.get_or_raise(session, camera_id)
    _validate_unique_codes(payload.slots)
    for entry in payload.slots:
        _validate_within_frame(entry, payload.src_frame_width, payload.src_frame_height)

    existing = {slot.code: slot for slot in camera_repository.list_slots(session, camera_id)}
    incoming_codes = {entry.code for entry in payload.slots}
    missing_codes = sorted(set(existing) - incoming_codes)
    if missing_codes and not payload.allow_delete:
        raise ConflictError(
            f"Replacing this map would delete codes {missing_codes} and their history; "
            "retry with allow_delete=true to confirm",
            code=ErrorCode.SLOT_MAP_INVALID,
        )

    before = _map_snapshot(camera_id, existing.values())
    for entry in payload.slots:
        slot = existing.get(entry.code)
        if slot is None:
            slot = ParkingSlot(camera_id=camera_id, code=entry.code)
            session.add(slot)
        slot.floor = entry.floor
        slot.polygon_json = [list(point) for point in entry.polygon.points]
        slot.src_frame_width = payload.src_frame_width
        slot.src_frame_height = payload.src_frame_height
    for code in missing_codes:
        session.delete(existing[code])
    session.flush()

    after_slots = camera_repository.list_slots(session, camera_id)
    audit_service.record(
        session,
        action=AuditAction.SLOT_MAP_UPDATED,
        username=actor.username,
        user_id=actor.id,
        entity_type="camera",
        entity_id=str(camera_id),
        before=before,
        after=_map_snapshot(camera_id, after_slots),
        client_ip=ctx.client_ip,
    )
    session.commit()
    ctx.request_reload(camera_id)  # AFTER commit - the loop must see the new rows
    return _to_response(camera_id, after_slots)


def _validate_unique_codes(entries: list[SlotMapEntry]) -> None:
    seen: set[str] = set()
    dupes: set[str] = set()
    for entry in entries:
        (dupes if entry.code in seen else seen).add(entry.code)
    if dupes:
        raise ConflictError(
            f"Duplicate slot codes in request: {sorted(dupes)}", code=ErrorCode.SLOT_CODE_TAKEN
        )


def _validate_within_frame(entry: SlotMapEntry, width: int, height: int) -> None:
    for x, y in entry.polygon.points:
        if x > width or y > height:
            raise ValidationFailedError(
                f"Slot {entry.code!r} has a point outside the {width}x{height} frame",
                code=ErrorCode.SLOT_MAP_FRAME_MISMATCH,
            )


def _map_snapshot(camera_id: int, slots: Iterable[ParkingSlot]) -> dict[str, object]:
    """Codes and count only, not full polygons - proportionate for an audit
    row (the row itself is the source of truth for the actual shapes)."""
    return {"camera_id": camera_id, "codes": sorted(slot.code for slot in slots)}


def _to_response(camera_id: int, slots: list[ParkingSlot]) -> SlotMapResponse:
    width = slots[0].src_frame_width if slots else 0
    height = slots[0].src_frame_height if slots else 0
    return SlotMapResponse(
        camera_id=camera_id,
        src_frame_width=width,
        src_frame_height=height,
        slots=[
            SlotMapEntry(
                code=slot.code,
                floor=slot.floor,
                polygon=PolygonModel(points=[(x, y) for x, y in slot.polygon_json]),
            )
            for slot in slots
        ],
    )
