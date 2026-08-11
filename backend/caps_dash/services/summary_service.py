"""Occupancy summary: counts only, aggregated in one grouped query.

Returns the response schema directly rather than an ORM object for the route
to convert - unlike `User` or `ParkingSlot`, `OccupancySummary` has no backing
table row; it is a pure aggregate over `parking_slots.current_state`, so there
is nothing for a `model_validate(from_attributes=True)` step to add.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from ..api.schemas.summary_schemas import FloorSummary, OccupancySummary
from ..db.enums import SlotState
from ..db.types import utc_now
from ..repositories import slot_repository

_ZERO_COUNTS: dict[str, int] = dict.fromkeys((state.value for state in SlotState), 0)


def get_summary(session: Session) -> OccupancySummary:
    """Aggregate over `current_state`, grouped by floor, in one SQL query.

    No slot ids, codes or camera ids ever enter this function - the grouped
    query in `slot_repository` is the privacy boundary, not a filter applied
    afterwards here.
    """
    counts_by_floor: dict[str, dict[str, int]] = defaultdict(lambda: dict(_ZERO_COUNTS))
    for floor, state, count in slot_repository.count_by_floor_and_state(session):
        counts_by_floor[floor][state] = count

    by_floor = [
        FloorSummary(
            floor=floor,
            total=sum(counts.values()),
            free=counts[SlotState.FREE],
            occupied=counts[SlotState.OCCUPIED],
            unknown=counts[SlotState.UNKNOWN],
        )
        for floor, counts in sorted(counts_by_floor.items())
    ]

    # Newest state_since across active slots; utc_now() when there are none
    # (an empty parking_slots table, e.g. a fresh install).
    updated_at = slot_repository.latest_state_since(session) or utc_now()

    return OccupancySummary(
        total=sum(floor_summary.total for floor_summary in by_floor),
        free=sum(floor_summary.free for floor_summary in by_floor),
        occupied=sum(floor_summary.occupied for floor_summary in by_floor),
        unknown=sum(floor_summary.unknown for floor_summary in by_floor),
        by_floor=by_floor,
        updated_at=updated_at,
    )
