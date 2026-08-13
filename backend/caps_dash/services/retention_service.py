"""Deleting data past its retention window.

Two independent cleanups live here: the admin-facing `/system/purge` (history
+ alerts, dry-run aware, always audited) and the background sweep of expired
`refresh_sessions` (`rate_limiter_sweep_job.py`'s other half - unrelated to
retention months, but a delete-old-rows job like this one, so it lives next
to it rather than in a third module).

`hourly_stats` is deliberately NEVER purged here. It exists precisely so
long-term trends survive after `slot_state_history` - the flash-wear
concern `retention_months` exists for - is gone; purging both together would
defeat the reason the aggregate table exists at all.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select
from sqlalchemy.orm import Session

from ..config.settings import Settings
from ..db.enums import AuditAction
from ..db.models import Alert, PlateRead, RefreshSession, SlotStateHistory
from ..db.types import utc_now
from . import audit_service

# Deletes commit in batches so a long purge never holds the write lock for
# the whole operation - a single multi-hundred-thousand-row transaction is
# exactly the kind of stall the phase-13 plan calls out as a risk on a board
# that also has to keep every camera loop fed.
HISTORY_BATCH_SIZE = 5000


@dataclass(slots=True, frozen=True)
class PurgeResult:
    deleted_history_rows: int
    deleted_alert_rows: int
    deleted_plate_rows: int = 0


def purge(
    session: Session,
    *,
    settings: Settings,
    older_than_months: int | None,
    dry_run: bool,
    actor_username: str,
    actor_user_id: int | None = None,
    client_ip: str = "",
    now: dt.datetime | None = None,
) -> PurgeResult:
    """Delete `slot_state_history` and acknowledged `alerts` older than the
    cutoff - or, with `dry_run=True`, only count what would be deleted.

    Unacknowledged alerts are never purged regardless of age: an open alert
    represents an unresolved condition, and deleting it silently would hide
    that from the next person who looks. `audit_logs` is never touched here
    either (see `implementation-steps` in the phase-13 plan) - a purge should
    itself remain forever auditable, which a self-purging audit trail cannot
    guarantee.
    """
    moment = now or utc_now()
    months = older_than_months or settings.retention_months
    cutoff = _months_before(moment, months)

    if dry_run:
        history_count = _count_history_before(session, cutoff)
        alert_count = _count_purgeable_alerts_before(session, cutoff)
        plate_count = _count_plate_reads_before(session, cutoff)
    else:
        history_count = _delete_history_before(session, cutoff)
        alert_count = _delete_purgeable_alerts_before(session, cutoff)
        plate_count = _delete_plate_reads_before(session, cutoff)

    audit_service.record(
        session,
        action=AuditAction.DATA_PURGED,
        username=actor_username,
        user_id=actor_user_id,
        entity_type="retention",
        entity_id=cutoff.date().isoformat(),
        after={
            "dry_run": dry_run,
            "cutoff": cutoff.isoformat(),
            "history_rows": history_count,
            "alert_rows": alert_count,
            "plate_rows": plate_count,
        },
        client_ip=client_ip,
    )
    session.commit()
    return PurgeResult(
        deleted_history_rows=history_count,
        deleted_alert_rows=alert_count,
        deleted_plate_rows=plate_count,
    )


def _count_plate_reads_before(session: Session, cutoff: dt.datetime) -> int:
    return int(
        session.execute(
            select(func.count()).select_from(PlateRead).where(PlateRead.read_at < cutoff)
        ).scalar_one()
    )


def _delete_plate_reads_before(session: Session, cutoff: dt.datetime) -> int:
    """Plate readings expire on the same schedule as occupancy history.

    Not a separate, longer window. A plate identifies a vehicle and through it
    a person, so it is the row in this database with the strongest claim to a
    short life - keeping it after the occupancy record it describes has gone
    would leave the identifying half of the pair behind and the innocuous half
    deleted, which is exactly backwards.
    """
    result = session.execute(delete(PlateRead).where(PlateRead.read_at < cutoff))
    session.commit()
    return int(getattr(result, "rowcount", 0) or 0)


def purge_expired_refresh_sessions(session: Session, *, now: dt.datetime | None = None) -> int:
    """Delete refresh-session rows that can never be used again.

    A row that is expired, revoked or rotated has no further purpose - it
    exists only as a dead end for reuse detection, and keeping every one
    forever makes the table grow without bound (validation session 1).
    """
    moment = now or utc_now()
    stmt = delete(RefreshSession).where(
        (RefreshSession.expires_at <= moment)
        | RefreshSession.revoked_at.is_not(None)
        | RefreshSession.rotated_at.is_not(None)
    )
    result = cast(CursorResult[Any], session.execute(stmt))
    session.commit()
    return int(result.rowcount)


def _months_before(moment: dt.datetime, months: int) -> dt.datetime:
    """Subtract whole months without pulling in a calendar dependency for
    one calculation - years and months are just base-12 arithmetic.
    """
    total_months = moment.year * 12 + (moment.month - 1) - months
    year, month = divmod(total_months, 12)
    day = min(moment.day, _days_in_month(year, month + 1))
    return moment.replace(year=year, month=month + 1, day=day)


def _days_in_month(year: int, month: int) -> int:
    next_month = dt.date(year + 1, 1, 1) if month == 12 else dt.date(year, month + 1, 1)
    return (next_month - dt.date(year, month, 1)).days


def _count_history_before(session: Session, cutoff: dt.datetime) -> int:
    stmt = select(func.count()).select_from(SlotStateHistory).where(
        SlotStateHistory.changed_at < cutoff
    )
    return int(session.execute(stmt).scalar_one())


def _count_purgeable_alerts_before(session: Session, cutoff: dt.datetime) -> int:
    stmt = select(func.count()).select_from(Alert).where(
        Alert.created_at < cutoff, Alert.acknowledged_at.is_not(None)
    )
    return int(session.execute(stmt).scalar_one())


def _delete_history_before(session: Session, cutoff: dt.datetime) -> int:
    total = 0
    while True:
        batch_ids = session.execute(
            select(SlotStateHistory.id)
            .where(SlotStateHistory.changed_at < cutoff)
            .limit(HISTORY_BATCH_SIZE)
        ).scalars().all()
        if not batch_ids:
            break
        session.execute(delete(SlotStateHistory).where(SlotStateHistory.id.in_(batch_ids)))
        session.commit()
        total += len(batch_ids)
    return total


def _delete_purgeable_alerts_before(session: Session, cutoff: dt.datetime) -> int:
    # Alert volume is inherently small (deduplication and cooldown keep it
    # that way - see `alert_service.create_deduplicated`), so a single
    # statement is fine here without the batching the history table needs.
    count = _count_purgeable_alerts_before(session, cutoff)
    session.execute(
        delete(Alert).where(Alert.created_at < cutoff, Alert.acknowledged_at.is_not(None))
    )
    session.commit()
    return count
