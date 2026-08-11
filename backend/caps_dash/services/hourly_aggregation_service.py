"""Rolling `slot_state_history` forward into `hourly_stats`.

Recomputing a report from raw history on this board's CPU is too slow to be
usable; this job runs the roll-up once per closed hour and reports read from
`hourly_stats` instead (see `stats_service.py`). The sweep itself lives in
`hourly_timeline.py`; the rollup and upsert live in `hourly_stat_writer.py`;
this module owns only deciding WHICH hours to process.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from ..db.enums import ScopeType
from ..db.types import utc_now
from ..observability.logging_setup import get_logger
from ..repositories import history_repository, stat_repository
from . import hourly_stat_writer
from .hourly_timeline import SlotHourAccumulator, compute_hour_timeline

logger = get_logger(__name__)

# Caps how many hours one job tick will catch up. Without a cap, a fresh
# deploy or a multi-day outage turns the FIRST job run into a long transaction
# competing with inference for the one CPU; later ticks finish the backlog.
MAX_HOURS_PER_RUN = 24


def _floor_hour(moment: dt.datetime) -> dt.datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


def hours_pending(
    session: Session, *, now: dt.datetime, max_hours: int = MAX_HOURS_PER_RUN
) -> list[dt.datetime]:
    """Closed hours with no aggregate yet, oldest first, capped at `max_hours`.

    "Closed" means the hour has fully elapsed - the in-progress hour is never
    aggregated, since its `unknown/free/occupied_seconds` would still be
    growing. The SITE scope's row is the completion marker (see
    `stat_repository.latest_aggregated_hour`): it is written last for every
    hour this job processes.
    """
    latest_closed = _floor_hour(now) - dt.timedelta(hours=1)
    last_done = stat_repository.latest_aggregated_hour(session)
    if last_done is not None:
        start = last_done + dt.timedelta(hours=1)
    else:
        earliest = history_repository.earliest_change_at(session)
        if earliest is None:
            return []  # nothing written yet; nothing to aggregate
        start = _floor_hour(earliest)

    hours: list[dt.datetime] = []
    cursor = start
    while cursor <= latest_closed and len(hours) < max_hours:
        hours.append(cursor)
        cursor += dt.timedelta(hours=1)
    return hours


def aggregate_pending_hours(session: Session, *, now: dt.datetime | None = None) -> int:
    """Aggregate every closed hour not yet summarised. Returns hours processed."""
    moment = now or utc_now()
    hours = hours_pending(session, now=moment)
    for hour_start in hours:
        _aggregate_one_hour(session, hour_start)
    if hours:
        logger.info("hourly_aggregation_completed", hours=len(hours))
    return len(hours)


def rebuild_hours(session: Session, *, since: dt.datetime, until: dt.datetime) -> int:
    """Force-recompute every hour in `[since, until]`, aggregated before or
    not. Safe to call anytime: the upsert makes each hour idempotent. Backs
    the `rebuild-stats` CLI command, e.g. after fixing a bug in this module.
    """
    count = 0
    cursor = _floor_hour(since)
    end = _floor_hour(until)
    while cursor <= end:
        _aggregate_one_hour(session, cursor)
        cursor += dt.timedelta(hours=1)
        count += 1
    return count


def _aggregate_one_hour(session: Session, hour_start: dt.datetime) -> None:
    hour_end = hour_start + dt.timedelta(hours=1)
    slot_floor = dict(stat_repository.active_slots(session))
    slot_ids = list(slot_floor)

    events = stat_repository.events_in_hour(
        session, hour_start=hour_start, hour_end=hour_end, slot_ids=slot_ids
    )
    if events and all(clock_suspect for *_rest, clock_suspect in events):
        # Every write this hour happened while the clock was implausible (a
        # fresh boot before NTP sync) - the bucket itself cannot be trusted.
        # Skip rather than aggregate garbage into a permanent row; a later
        # run, once real events land in this hour, will pick it up.
        logger.warning("hourly_aggregation_skipped_all_suspect", hour_start=hour_start.isoformat())
        return

    seeds = stat_repository.seed_states_before(session, before=hour_start, slot_ids=slot_ids)
    timeline = compute_hour_timeline(
        hour_start=hour_start,
        hour_end=hour_end,
        slot_floor=slot_floor,
        seed_states=seeds,
        events=events,
    )

    for slot_id, acc in timeline.slots.items():
        hourly_stat_writer.upsert(
            session,
            scope_type=ScopeType.SLOT,
            scope_key=str(slot_id),
            hour_start=hour_start,
            acc=acc,
            peak_occupied=1 if acc.occupied_seconds > 0 else 0,
            slot_count=1,
        )

    floor_totals = hourly_stat_writer.rollup(timeline.slots, group_key=lambda acc: acc.floor)
    for floor, acc in floor_totals.items():
        hourly_stat_writer.upsert(
            session,
            scope_type=ScopeType.FLOOR,
            scope_key=floor,
            hour_start=hour_start,
            acc=acc,
            peak_occupied=timeline.peak_occupied_by_floor.get(floor, 0),
            slot_count=sum(1 for f in slot_floor.values() if f == floor),
        )

    site_totals = hourly_stat_writer.rollup(timeline.slots, group_key=lambda _acc: "")
    site_acc = site_totals.get("", SlotHourAccumulator(floor=""))
    hourly_stat_writer.upsert(
        session,
        scope_type=ScopeType.SITE,
        scope_key="",
        hour_start=hour_start,
        acc=site_acc,
        peak_occupied=timeline.peak_occupied_site,
        slot_count=len(slot_floor),
    )
    session.commit()
