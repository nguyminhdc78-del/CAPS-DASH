"""Parking slot queries.

`select()` statements only. Query boundaries, not row-level filters, enforce
privacy: the query layer selects exactly the columns an endpoint is allowed to
return, so a code change cannot accidentally hand `camera_id` or `polygon` to
an unauthenticated response. Two examples:

1. `count_by_floor_and_state()` backs the authenticated `/api/summary` - counts
   only, no codes or IDs.
2. `list_free_codes_by_floor()` backs the public `/api/public/summary` - FREE
   codes only, no occupied codes, camera IDs or polygons.

Both read `parking_slots.current_state`, the column phase 06 denormalises onto
the slot row, so neither endpoint ever touches `slot_state_history`.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from ..db.enums import SlotState
from ..db.models import ParkingSlot
from ..errors.codes import ErrorCode
from ..errors.exceptions import NotFoundError


def get_by_id(session: Session, slot_id: int) -> ParkingSlot | None:
    return session.get(ParkingSlot, slot_id)


def get_or_raise(session: Session, slot_id: int) -> ParkingSlot:
    slot = get_by_id(session, slot_id)
    if slot is None:
        raise NotFoundError(f"No slot with id {slot_id}", code=ErrorCode.NOT_FOUND)
    return slot


def get_by_camera_and_code(
    session: Session, camera_id: int, code: str, *, exclude_id: int | None = None
) -> ParkingSlot | None:
    """Used to enforce code-uniqueness within one camera before a rename commits."""
    query = select(ParkingSlot).where(
        ParkingSlot.camera_id == camera_id, ParkingSlot.code == code
    )
    if exclude_id is not None:
        query = query.where(ParkingSlot.id != exclude_id)
    return session.execute(query).scalar_one_or_none()


def list_query(
    *, floor: str | None, camera_id: int | None, state: str | None
) -> Select[Any]:
    """Filtered, deterministically ordered statement. Not executed here.

    Left as a statement (not a list) so `api/pagination.py`'s `count_rows` and
    `apply_page` can both build on it - one query shape shared for counting
    and for the paged fetch, rather than a second, subtly different one.
    """
    query = select(ParkingSlot)
    if floor is not None:
        query = query.where(ParkingSlot.floor == floor)
    if camera_id is not None:
        query = query.where(ParkingSlot.camera_id == camera_id)
    if state is not None:
        query = query.where(ParkingSlot.current_state == state)
    return query.order_by(ParkingSlot.floor, ParkingSlot.code)


def count_by_floor_and_state(session: Session) -> list[tuple[str, str, int]]:
    """One grouped aggregate for `/summary`.

    Rows are never loaded and counted in Python: that would mean the query
    layer hands a slot's code and camera id up toward a resident-facing route,
    exactly the leak the privacy split exists to prevent. Restricted to
    `is_active` - a disabled slot should not appear in a count residents see.
    """
    query = (
        select(ParkingSlot.floor, ParkingSlot.current_state, func.count(ParkingSlot.id))
        .where(ParkingSlot.is_active.is_(True))
        .group_by(ParkingSlot.floor, ParkingSlot.current_state)
    )
    return [(floor, state, count) for floor, state, count in session.execute(query)]


def list_free_codes_by_floor(session: Session) -> list[tuple[str, str]]:
    """FREE bay codes for the public kiosk - one column-level query.

    Selects `(floor, code)` columns, not `ParkingSlot` rows: a row also
    carries `polygon_json` and `camera_id`, and this result reaches an
    unauthenticated response. Same idiom as `count_by_floor_and_state`
    above - the query is the privacy boundary, not a filter applied to
    loaded rows afterwards. FREE only, so an occupied bay's code can never
    appear here even if a caller asked for it; restricted to `is_active`,
    same as the counts.
    """
    query = (
        select(ParkingSlot.floor, ParkingSlot.code)
        .where(ParkingSlot.current_state == SlotState.FREE, ParkingSlot.is_active.is_(True))
        .order_by(ParkingSlot.floor, ParkingSlot.code)
    )
    return [(floor, code) for floor, code in session.execute(query)]


def latest_state_since(session: Session) -> dt.datetime | None:
    """Newest `state_since` among active slots - the summary's `updated_at`."""
    query = select(func.max(ParkingSlot.state_since)).where(ParkingSlot.is_active.is_(True))
    return session.execute(query).scalar_one_or_none()
