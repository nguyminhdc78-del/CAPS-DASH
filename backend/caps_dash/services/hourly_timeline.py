"""Reconstructing one hour's per-slot state timeline from history rows.

Split out of `hourly_aggregation_service.py` to keep both files under the
200-line convention: this module is the O(slots + events) sweep; the other
module is upsert orchestration. Pure computation, no session writes, so it is
unit-testable without a database if that is ever needed.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from ..db.enums import SlotState


@dataclass(slots=True)
class SlotHourAccumulator:
    """Seconds-per-state for one slot across one hour, plus bookkeeping."""

    floor: str
    occupied_seconds: float = 0.0
    free_seconds: float = 0.0
    unknown_seconds: float = 0.0
    change_count: int = 0
    clock_suspect: bool = False

    def add(self, state: str, seconds: float) -> None:
        if seconds <= 0:
            return
        if state == SlotState.OCCUPIED:
            self.occupied_seconds += seconds
        elif state == SlotState.FREE:
            self.free_seconds += seconds
        else:
            self.unknown_seconds += seconds


@dataclass(slots=True)
class HourTimeline:
    """The whole hour's result: every slot's accumulator plus the peak
    concurrently-OCCUPIED count, both per floor and site-wide.
    """

    slots: dict[int, SlotHourAccumulator]
    peak_occupied_by_floor: dict[str, int]
    peak_occupied_site: int


def compute_hour_timeline(
    *,
    hour_start: dt.datetime,
    hour_end: dt.datetime,
    slot_floor: dict[int, str],
    seed_states: dict[int, str],
    events: list[tuple[int, str, dt.datetime, bool]],
) -> HourTimeline:
    """Sweep `events` (already `(slot_id, new_state, changed_at,
    clock_suspect)`, oldest first - see `stat_repository.events_in_hour`)
    against each slot's state as of `hour_start` (`seed_states`, from
    `stat_repository.seed_states_before`; a slot missing from it defaults to
    UNKNOWN).

    Each slot accumulates duration against only ITS OWN previous event (an
    O(events) walk, not O(slots x events) re-scanning every slot on every
    event) - the difference matters at the stated non-functional target of
    "one hour across 200 slots < 2 s".
    """
    state: dict[int, str] = {
        slot_id: seed_states.get(slot_id, SlotState.UNKNOWN) for slot_id in slot_floor
    }
    last_update: dict[int, dt.datetime] = dict.fromkeys(slot_floor, hour_start)
    acc = {slot_id: SlotHourAccumulator(floor=floor) for slot_id, floor in slot_floor.items()}

    concurrent_site = sum(1 for current in state.values() if current == SlotState.OCCUPIED)
    concurrent_floor: dict[str, int] = defaultdict(int)
    for slot_id, current in state.items():
        if current == SlotState.OCCUPIED:
            concurrent_floor[slot_floor[slot_id]] += 1
    peak_site = concurrent_site
    peak_floor: dict[str, int] = dict(concurrent_floor)

    for slot_id, new_state, changed_at, clock_suspect in events:
        if slot_id not in acc:
            continue  # a now-inactive slot's history; not part of this rollup
        elapsed = (changed_at - last_update[slot_id]).total_seconds()
        acc[slot_id].add(state[slot_id], elapsed)
        acc[slot_id].change_count += 1
        acc[slot_id].clock_suspect = acc[slot_id].clock_suspect or clock_suspect

        old_state = state[slot_id]
        if old_state != new_state:
            floor = slot_floor[slot_id]
            if old_state == SlotState.OCCUPIED:
                concurrent_site -= 1
                concurrent_floor[floor] -= 1
            if new_state == SlotState.OCCUPIED:
                concurrent_site += 1
                concurrent_floor[floor] += 1
            peak_site = max(peak_site, concurrent_site)
            peak_floor[floor] = max(peak_floor.get(floor, 0), concurrent_floor[floor])

        state[slot_id] = new_state
        last_update[slot_id] = changed_at

    for slot_id in slot_floor:
        tail = (hour_end - last_update[slot_id]).total_seconds()
        acc[slot_id].add(state[slot_id], tail)

    return HourTimeline(
        slots=acc, peak_occupied_by_floor=dict(peak_floor), peak_occupied_site=peak_site
    )
