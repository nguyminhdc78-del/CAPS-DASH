"""Slot state history: mandatory, capped date range then a filtered page.

The range guard exists for a concrete reason: `slot_state_history` is the
largest table in the system, it lives on flash storage behind a CPU shared
with every camera loop, and a single unbounded scan is enough to stall all of
them behind one HTTP request. So a range always exists (defaulted when the
caller omits it) and is always capped, before any query runs.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from sqlalchemy.orm import Session

from ..api.pagination import PageParams, apply_page, count_rows
from ..config.settings import Settings
from ..db.models import SlotStateHistory
from ..errors.codes import ErrorCode
from ..errors.exceptions import ValidationFailedError
from ..repositories import history_repository


def resolve_range(
    since: dt.datetime | None, until: dt.datetime | None, settings: Settings
) -> tuple[dt.datetime, dt.datetime]:
    """Fill in the default span and enforce the maximum one.

    `since`/`until` are already timezone-aware here - the route's query
    parameters are typed `AwareDatetime`, so pydantic rejects a naive
    timestamp before this function ever sees it.
    """
    resolved_until = until or dt.datetime.now(dt.UTC)
    resolved_since = since or (
        resolved_until - dt.timedelta(days=settings.history_default_span_days)
    )

    if resolved_since > resolved_until:
        raise ValidationFailedError(
            "`from` must not be after `to`", code=ErrorCode.RANGE_INVALID
        )

    span = resolved_until - resolved_since
    max_span = dt.timedelta(days=settings.history_max_span_days)
    if span > max_span:
        raise ValidationFailedError(
            f"Range exceeds the {settings.history_max_span_days}-day maximum",
            code=ErrorCode.RANGE_TOO_WIDE,
        )
    return resolved_since, resolved_until


def list_history(
    session: Session,
    settings: Settings,
    params: PageParams,
    *,
    since: dt.datetime | None = None,
    until: dt.datetime | None = None,
    slot_id: int | None = None,
    camera_code: str | None = None,
    floor: str | None = None,
) -> tuple[Sequence[SlotStateHistory], int]:
    """Filtered, newest-first page of state changes plus the unfiltered total."""
    range_since, range_until = resolve_range(since, until, settings)
    stmt = history_repository.build_range_query(
        since=range_since,
        until=range_until,
        slot_id=slot_id,
        camera_code=camera_code,
        floor=floor,
    )
    total = count_rows(session, stmt)
    rows = session.execute(apply_page(stmt, params)).scalars().all()
    return rows, total
