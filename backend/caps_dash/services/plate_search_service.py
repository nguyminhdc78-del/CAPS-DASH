"""Finding a car by its plate.

The question this exists for is a guard's: a resident cannot remember where
they parked, and the guard needs to tell them. So the answer is a BAY, not a
list of sightings - which shapes the query more than it sounds.

Three rules follow from that.

**One bay holds one car, so one bay has one plate.** Which plate is decided by
*consensus*, not by recency. Taking the newest reading looks right and is not:
measured on the board, bay A1 was read as `98A83355` nine times running at
0.61-0.91 confidence, then once as `88C27999` at 0.54 - and that single
misread became the bay's answer, so searching the real plate found nothing.
OCR misreads are individually random and collectively rare; the plate read
most often in a bay is the plate on the car in it.

**A reading the detector was unsure of is not evidence.** Below
`MIN_PLATE_CONFIDENCE` a reading is dropped before the vote, which is what
stops one bad frame outvoting nothing at all in a quiet bay. On the board,
four readings of fifty-nine fell below that line, and the misreads were among
them.

**A bay only counts while it is still occupied.** A reading from a bay that is
now FREE describes a car that has left. Sending a guard to it is worse than
saying nothing, because they will trust it and walk there.

Votes are scoped to the car currently parked - readings taken since the bay
last changed state. When a restart has reset that clock and no reading has
landed yet, the vote falls back to a recent window rather than answering
nothing, because "I cannot see your car" is the one answer a lost driver
cannot use.
"""

from __future__ import annotations

import dataclasses
import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.enums import SlotState
from ..db.models import Camera, ParkingSlot, PlateRead
from ..db.types import utc_now

# Enough to find a car, few enough that a mistyped query cannot pull the whole
# table into a browser.
MAX_RESULTS = 50

# Below three characters nearly every plate matches, so the search stops being
# a search. Rejected rather than silently truncated: an empty result is
# confusing, a stated reason is not.
MIN_QUERY_LENGTH = 3

# Readings the detector was less sure of than this never reach the vote.
# Measured on the board: 55 of 59 readings sat at or above 0.6, and both
# observed misreads (0.54, 0.45) sat below it. Set higher and a dim bay stops
# answering at all; set lower and single bad frames re-enter the count.
MIN_PLATE_CONFIDENCE = 0.6

# How far back the vote may reach when the bay's own state clock has been
# reset - a service restart re-derives every state, so `state_since` becomes
# the restart time and no reading is newer than it. Without this fallback the
# search goes blank after every deploy until each car is read again.
FALLBACK_WINDOW = dt.timedelta(hours=12)


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

    # Deciding the plate BEFORE matching the query is the whole point. Filtering
    # by plate first would find the best reading *of the plate asked for*, which
    # in a bay that has been misread once is a row nobody should trust, and in a
    # bay another car has since taken is somebody else's space.
    matches = [
        match for match in _current_plate_per_bay(session, occupied_only=occupied_only)
        if query in match.plate
    ]
    matches.sort(key=lambda match: match.read_at, reverse=True)
    return matches[:MAX_RESULTS]


def _current_plate_per_bay(session: Session, *, occupied_only: bool) -> list[PlateMatch]:
    """One PlateMatch per bay: the plate its readings agree on.

    Reductions happen in Python rather than SQL because "most frequent, then
    most confident, then newest" is three tie-breaks deep and reads as noise in
    a window function. The row set it works over is bounded twice - by the
    confidence floor and by `FALLBACK_WINDOW` - so this stays small.
    """
    cutoff = utc_now() - FALLBACK_WINDOW
    statement = (
        select(PlateRead, ParkingSlot, Camera)
        .join(ParkingSlot, PlateRead.slot_id == ParkingSlot.id)
        .join(Camera, PlateRead.camera_id == Camera.id)
        .where(
            PlateRead.read_at >= cutoff,
            ParkingSlot.is_active.is_(True),
        )
    )
    if occupied_only:
        statement = statement.where(ParkingSlot.current_state == SlotState.OCCUPIED)

    by_bay: dict[int, list[tuple[PlateRead, ParkingSlot, Camera]]] = {}
    for read, slot, camera in session.execute(statement).all():
        by_bay.setdefault(slot.id, []).append((read, slot, camera))

    return [_vote(rows) for rows in by_bay.values() if rows]


def _vote(rows: list[tuple[PlateRead, ParkingSlot, Camera]]) -> PlateMatch:
    """Pick the plate this bay's readings agree on, and the best row for it."""
    slot = rows[0][1]
    # Readings taken since the bay last changed state describe the car in it
    # now. If a restart reset that clock they will all be older, and voting on
    # an empty set would answer nothing - so fall back to every row in window.
    # `state_since` is nullable for a bay that has never resolved a state; that
    # is the same "no episode to scope to" case, handled the same way.
    since = slot.state_since
    current = [row for row in rows if since is None or row[0].read_at >= since] or rows

    # Confident readings decide the vote, but they do not gate the answer: a bay
    # read only ever at 0.31 still reports that plate, with its confidence
    # attached, because for a guard a poor reading is a lead to check rather
    # than nothing at all. Only when better readings exist do the poor ones lose.
    current = [row for row in current if row[0].confidence >= MIN_PLATE_CONFIDENCE] or current

    counts: dict[str, int] = {}
    for read, _, _ in current:
        counts[read.plate] = counts.get(read.plate, 0) + 1
    best_plate = max(
        counts,
        # Most readings wins. Then the most confident reading of each candidate.
        # Then the newest - which is what decides a bay whose previous car and
        # current car have each been read once: the car still there is the one
        # seen last, and guiding a guard to the earlier one sends them to a
        # stranger's car.
        key=lambda plate: (
            counts[plate],
            max(read.confidence for read, _, _ in current if read.plate == plate),
            max(read.read_at for read, _, _ in current if read.plate == plate),
        ),
    )

    read, slot, camera = max(
        (row for row in current if row[0].plate == best_plate),
        key=lambda row: (row[0].confidence, row[0].read_at),
    )
    return PlateMatch(
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
