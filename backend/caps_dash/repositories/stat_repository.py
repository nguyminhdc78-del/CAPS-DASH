"""Database access for pre-aggregated hourly occupancy.

`GET /stats/hourly` is implemented in phase 13 (see `api/routes/stats_routes.py`
for the frozen response schema and the current 501 stub). This repository
exists now so the query shape it will read from is decided at the same time
as the schema, rather than invented later against whatever `HourlyStat` looks
like by then.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from ..db.enums import ScopeType
from ..db.models import HourlyStat, ParkingSlot, SlotStateHistory


def build_scope_range_query(
    *, scope_type: str, scope_key: str, since: dt.datetime, until: dt.datetime
) -> Select[Any]:
    """Unexecuted statement: one scope's hourly rows for `[since, until]`."""
    return (
        select(HourlyStat)
        .where(
            HourlyStat.scope_type == scope_type,
            HourlyStat.scope_key == scope_key,
            HourlyStat.hour_start >= since,
            HourlyStat.hour_start <= until,
        )
        .order_by(HourlyStat.hour_start)
    )


def active_slots(session: Session) -> list[tuple[int, str]]:
    """`(slot_id, floor)` for every slot the aggregation job must account for.

    Restricted to `is_active` - a decommissioned slot's history still exists
    (and still counts toward `/history` and `/sessions`), but it should stop
    contributing fresh hourly rows once nobody expects it to have occupancy.
    """
    stmt = select(ParkingSlot.id, ParkingSlot.floor).where(ParkingSlot.is_active.is_(True))
    return [(slot_id, floor) for slot_id, floor in session.execute(stmt)]


def seed_states_before(
    session: Session, *, before: dt.datetime, slot_ids: list[int]
) -> dict[int, str]:
    """Each slot's state as of `before`: the `new_state` of its latest row
    strictly earlier than `before`.

    A window function (`ROW_NUMBER`) rather than one query per slot - both are
    portable SQL, but the loop version is O(slots) round-trips every hour,
    every job tick. Standard SQL, not a SQLite-only construct, so this stays
    engine-agnostic same as the rest of the data layer. A slot missing from
    the returned dict has no prior history; callers default it to UNKNOWN,
    matching `ParkingSlot.current_state`'s own default.
    """
    if not slot_ids:
        return {}
    rank = (
        func.row_number()
        .over(
            partition_by=SlotStateHistory.slot_id,
            order_by=SlotStateHistory.changed_at.desc(),
        )
        .label("rank")
    )
    ranked = (
        select(SlotStateHistory.slot_id, SlotStateHistory.new_state, rank)
        .where(
            SlotStateHistory.changed_at < before,
            SlotStateHistory.slot_id.in_(slot_ids),
        )
        .subquery()
    )
    stmt = select(ranked.c.slot_id, ranked.c.new_state).where(ranked.c.rank == 1)
    return {slot_id: new_state for slot_id, new_state in session.execute(stmt)}


def events_in_hour(
    session: Session, *, hour_start: dt.datetime, hour_end: dt.datetime, slot_ids: list[int]
) -> list[tuple[int, str, dt.datetime, bool]]:
    """`(slot_id, new_state, changed_at, clock_suspect)`, oldest first.

    One query for every slot in scope, not one per slot: this is the hot path
    of the aggregation job and runs every `settings.aggregation_interval_s`.
    """
    if not slot_ids:
        return []
    stmt = (
        select(
            SlotStateHistory.slot_id,
            SlotStateHistory.new_state,
            SlotStateHistory.changed_at,
            SlotStateHistory.clock_suspect,
        )
        .where(
            SlotStateHistory.changed_at >= hour_start,
            SlotStateHistory.changed_at < hour_end,
            SlotStateHistory.slot_id.in_(slot_ids),
        )
        .order_by(SlotStateHistory.changed_at, SlotStateHistory.id)
    )
    # `.tuples()` narrows `Result[Row[...]]` to plain tuples - both at
    # runtime (a `Row` already behaves like one) and for mypy, which
    # otherwise sees `Sequence[Row[...]]` here, not `list[tuple[...]]`.
    return list(session.execute(stmt).tuples().all())


def latest_aggregated_hour(session: Session) -> dt.datetime | None:
    """The newest `hour_start` already rolled up, using the SITE row as the
    marker - it is written last for every hour the job processes, so its
    presence means every scope for that hour is done.
    """
    stmt = select(func.max(HourlyStat.hour_start)).where(
        HourlyStat.scope_type == ScopeType.SITE, HourlyStat.scope_key == ""
    )
    return session.execute(stmt).scalar_one_or_none()
