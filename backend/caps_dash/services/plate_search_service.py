"""Finding a car by its plate.

The question this exists for is a guard's: a resident cannot remember where
they parked, and the guard needs to tell them. So the answer is a BAY, not a
list of sightings - which shapes the query more than it sounds.

Two rules follow from that.

**The newest reading per bay, not every reading.** A car that parked in B12
this morning and A03 this afternoon has two rows; only the second is where it
is. Older rows still matter - they are why a car that has since moved is
findable at all - but they must never outrank the current one.

**A bay only counts while it is still occupied.** A reading from a bay that is
now FREE describes a car that has left. Sending a guard to it is worse than
saying nothing, because they will trust it and walk there.
"""

from __future__ import annotations

import dataclasses
import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.enums import SlotState
from ..db.models import Camera, ParkingSlot, PlateRead

# Enough to find a car, few enough that a mistyped query cannot pull the whole
# table into a browser.
MAX_RESULTS = 50

# Below three characters nearly every plate matches, so the search stops being
# a search. Rejected rather than silently truncated: an empty result is
# confusing, a stated reason is not.
MIN_QUERY_LENGTH = 3


@dataclasses.dataclass(frozen=True, slots=True)
class PlateMatch:
    """One car, where it is, and how much to trust the reading."""

    plate: str
    slot_code: str
    floor: str
    camera_id: int
    camera_code: str
    slot_state: str
    read_at: dt.datetime
    confidence: float
    plate_width_px: int


def normalise_query(raw: str) -> str:
    """`30H-832.31` and `30h 832 31` are the same search.

    Plates are stored with separators stripped because the punctuation is a
    rendering convention that varies between plates. A guard typing what they
    see on a windscreen should not have to guess which convention the database
    used.
    """
    return "".join(ch for ch in raw.upper() if ch.isalnum())


def search(session: Session, raw_query: str, *, occupied_only: bool = True) -> list[PlateMatch]:
    """Bays whose most recent plate reading matches, newest first.

    `occupied_only` defaults to True because the question is "where is this
    car now". Turning it off answers "where was it last seen", which is a
    different and rarer question - an investigation rather than a lost driver.
    """
    query = normalise_query(raw_query)
    if len(query) < MIN_QUERY_LENGTH:
        return []

    # The latest reading per slot, computed first. Filtering by plate before
    # this would find the newest reading *of that plate*, which is a different
    # row whenever another car has since parked in the same bay - and would
    # send a guard to a space now holding somebody else.
    newest = (
        select(PlateRead.slot_id, func.max(PlateRead.read_at).label("read_at"))
        .group_by(PlateRead.slot_id)
        .subquery()
    )

    statement = (
        select(PlateRead, ParkingSlot, Camera)
        .join(
            newest,
            (PlateRead.slot_id == newest.c.slot_id) & (PlateRead.read_at == newest.c.read_at),
        )
        .join(ParkingSlot, PlateRead.slot_id == ParkingSlot.id)
        .join(Camera, PlateRead.camera_id == Camera.id)
        .where(PlateRead.plate.contains(query))
        .order_by(PlateRead.read_at.desc())
        .limit(MAX_RESULTS)
    )
    if occupied_only:
        statement = statement.where(ParkingSlot.current_state == SlotState.OCCUPIED)

    return [
        PlateMatch(
            plate=read.plate,
            slot_code=slot.code,
            floor=slot.floor,
            camera_id=camera.id,
            camera_code=camera.code,
            slot_state=str(slot.current_state),
            read_at=read.read_at,
            confidence=read.confidence,
            plate_width_px=read.plate_width_px,
        )
        for read, slot, camera in session.execute(statement).all()
    ]
