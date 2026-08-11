"""Turning a hour's `SlotHourAccumulator`s into `HourlyStat` rows.

Split out of `hourly_aggregation_service.py` to keep both under the 200-line
convention: that module decides WHICH hours to process; this one owns the
floor/site rollup and the upsert itself.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import HourlyStat
from .hourly_timeline import SlotHourAccumulator


def rollup(
    per_slot: dict[int, SlotHourAccumulator],
    *,
    group_key: Callable[[SlotHourAccumulator], str],
) -> dict[str, SlotHourAccumulator]:
    """Sum per-slot accumulators into groups (by floor, or all into one site
    bucket via a key function that always returns `""`). Durations and change
    counts are additive; `clock_suspect` is OR-reduced - one suspect slot is
    enough to flag the whole scope's hour.
    """
    rolled: dict[str, SlotHourAccumulator] = {}
    for acc in per_slot.values():
        bucket = group_key(acc)
        target = rolled.setdefault(bucket, SlotHourAccumulator(floor=bucket))
        target.occupied_seconds += acc.occupied_seconds
        target.free_seconds += acc.free_seconds
        target.unknown_seconds += acc.unknown_seconds
        target.change_count += acc.change_count
        target.clock_suspect = target.clock_suspect or acc.clock_suspect
    return rolled


def upsert(
    session: Session,
    *,
    scope_type: str,
    scope_key: str,
    hour_start: dt.datetime,
    acc: SlotHourAccumulator,
    peak_occupied: int,
    slot_count: int,
) -> None:
    """Select-then-update/insert, not `ON CONFLICT` - portable across the
    SQLite deployment and a future Postgres one (phase 02). Re-running this
    for the same `(scope_type, scope_key, hour_start)` overwrites the same
    row rather than inserting a duplicate; see `test_hourly_aggregation_
    idempotent.py`.
    """
    existing = session.execute(
        select(HourlyStat).where(
            HourlyStat.scope_type == scope_type,
            HourlyStat.scope_key == scope_key,
            HourlyStat.hour_start == hour_start,
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = HourlyStat(scope_type=scope_type, scope_key=scope_key, hour_start=hour_start)
        session.add(existing)

    existing.occupied_seconds = acc.occupied_seconds
    existing.free_seconds = acc.free_seconds
    existing.unknown_seconds = acc.unknown_seconds
    existing.change_count = acc.change_count
    existing.peak_occupied = peak_occupied
    existing.slot_count = slot_count
    existing.clock_suspect = acc.clock_suspect
