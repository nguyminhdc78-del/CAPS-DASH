"""`GET /stats/hourly`: read pre-aggregated rows, never raw history.

Recomputing from `slot_state_history` on every request is exactly what
`hourly_aggregation_service.py` exists to avoid; this module only ever reads
`hourly_stats`.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from sqlalchemy.orm import Session

from ..api.pagination import PageParams, apply_page, count_rows
from ..config.settings import Settings
from ..db.models import HourlyStat
from ..repositories import stat_repository
from . import history_service


def list_hourly_stats(
    session: Session,
    settings: Settings,
    params: PageParams,
    *,
    scope_type: str,
    scope_key: str,
    since: dt.datetime | None,
    until: dt.datetime | None,
) -> tuple[Sequence[HourlyStat], int]:
    """Oldest-first page of hourly rows for one scope, plus the total.

    Reuses `history_service.resolve_range` for the same mandatory-and-capped
    range `/history` enforces. `hourly_stats` is far smaller than raw
    history, but an unbounded range is still an unbounded response on a board
    with limited memory.
    """
    range_since, range_until = history_service.resolve_range(since, until, settings)
    stmt = stat_repository.build_scope_range_query(
        scope_type=scope_type, scope_key=scope_key, since=range_since, until=range_until
    )
    total = count_rows(session, stmt)
    rows = session.execute(apply_page(stmt, params)).scalars().all()
    return rows, total
