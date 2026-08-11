"""Database access for slot state history - the largest table in the system.

`select()` statements only, built but never executed here. `slot_state_history`
sits on flash storage behind a CPU shared with every camera loop, so the
service layer (not this module) is where the mandatory date range is enforced
before any of these statements ever run. Filters below read the columns
`SlotStateHistory` denormalises onto each row (`camera_code`, `slot_code`,
`floor`) precisely so this hot path never joins to `parking_slots` or
`cameras`.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from ..db.models import SlotStateHistory


def build_range_query(
    *,
    since: dt.datetime,
    until: dt.datetime,
    slot_id: int | None = None,
    camera_code: str | None = None,
    floor: str | None = None,
) -> Select[Any]:
    """Unexecuted, newest-first statement for `[since, until]`.

    The service applies pagination (`api/pagination.py`) on top of this; the
    ordering is fixed here because "newest first" is a contract of the
    `/history` endpoint, not a per-request choice.
    """
    stmt = select(SlotStateHistory).where(
        SlotStateHistory.changed_at >= since,
        SlotStateHistory.changed_at <= until,
    )
    if slot_id is not None:
        stmt = stmt.where(SlotStateHistory.slot_id == slot_id)
    if camera_code:
        stmt = stmt.where(SlotStateHistory.camera_code == camera_code)
    if floor:
        stmt = stmt.where(SlotStateHistory.floor == floor)
    return stmt.order_by(SlotStateHistory.changed_at.desc())


def latest_for_slot(session: Session, slot_id: int) -> SlotStateHistory | None:
    """The single most recent row for one slot, or `None` with no history yet.

    Used by `overstay_alert_job` to check whether the row that set a slot's
    current `state_since` was written under a suspect clock - if so, the
    overstay duration derived from it cannot be trusted, and the job must not
    alert on it.
    """
    stmt = (
        select(SlotStateHistory)
        .where(SlotStateHistory.slot_id == slot_id)
        .order_by(SlotStateHistory.changed_at.desc(), SlotStateHistory.id.desc())
        .limit(1)
    )
    return session.execute(stmt).scalars().first()


def earliest_change_at(session: Session) -> dt.datetime | None:
    """The oldest `changed_at` in the whole table, or `None` if it is empty.

    Bounds the first run of the hourly aggregation job and the `rebuild-stats`
    CLI command: without it, "aggregate every hour that has never been
    aggregated" has no starting point other than the Unix epoch.
    """
    return session.execute(select(func.min(SlotStateHistory.changed_at))).scalar_one_or_none()
