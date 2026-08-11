"""Database access for cameras and their slot maps.

Repositories keep the queries in one place so services read as business logic
rather than SQL - see `user_repository.py` for the same rationale. Slot rows
live here too, not in a separate `slot_repository`: the bulk slot-map replace
this phase owns (`slot_map_service.py`) is a camera-scoped operation end to
end, and splitting its queries into a module owned by a different phase would
only add an import across a file-ownership boundary for no benefit.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Camera, ParkingSlot
from ..errors.exceptions import NotFoundError


def get_or_raise(session: Session, camera_id: int) -> Camera:
    camera = session.get(Camera, camera_id)
    if camera is None:
        raise NotFoundError(f"No camera with id {camera_id}")
    return camera


def get_by_code(session: Session, code: str) -> Camera | None:
    return session.execute(select(Camera).where(Camera.code == code)).scalar_one_or_none()


def list_page_with_slot_counts(
    session: Session, *, limit: int, offset: int
) -> tuple[list[tuple[Camera, int]], int]:
    """One aggregate query for the page, one count query for the total.

    A per-camera `SELECT count(*) FROM parking_slots WHERE camera_id = ?`
    looks innocent with two test cameras and turns `/cameras` into N+1 queries
    once a real site has thirty of them - this stays at exactly two
    statements regardless of how many cameras exist.
    """
    total = int(session.execute(select(func.count(Camera.id))).scalar_one())
    stmt = (
        select(Camera, func.count(ParkingSlot.id))
        .outerjoin(ParkingSlot, ParkingSlot.camera_id == Camera.id)
        .group_by(Camera.id)
        .order_by(Camera.code)
        .limit(limit)
        .offset(offset)
    )
    rows = [(camera, int(count)) for camera, count in session.execute(stmt).all()]
    return rows, total


def count_slots(session: Session, camera_id: int) -> int:
    stmt = select(func.count(ParkingSlot.id)).where(ParkingSlot.camera_id == camera_id)
    return int(session.execute(stmt).scalar_one())


def list_slots(session: Session, camera_id: int) -> list[ParkingSlot]:
    """Every slot drawn on this camera, active or not - what the ROI editor edits."""
    stmt = (
        select(ParkingSlot).where(ParkingSlot.camera_id == camera_id).order_by(ParkingSlot.code)
    )
    return list(session.execute(stmt).scalars())


def delete(session: Session, camera: Camera) -> None:
    """Cascades slots, and through them `slot_state_history`, in one statement.

    `Camera.slots` carries `cascade="all, delete-orphan", passive_deletes=True`
    and the FK is `ondelete="CASCADE"` with `PRAGMA foreign_keys=ON` (see
    `engine_factory.py`) - the database removes the children, so no manual
    per-slot delete loop is needed or wanted here.
    """
    session.delete(camera)
