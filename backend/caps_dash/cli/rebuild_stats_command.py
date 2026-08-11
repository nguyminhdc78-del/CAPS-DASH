"""`caps-dash rebuild-stats` - force-recompute `hourly_stats` over a range.

For after a bug fix in `hourly_aggregation_service.py`, or to backfill a gap.
Safe to run anytime: the aggregation upsert is idempotent, so recomputing an
hour that already has a row simply overwrites it with the same (or corrected)
numbers rather than duplicating anything.
"""

from __future__ import annotations

import argparse
import datetime as dt
from typing import Any

from ..config.settings import get_settings
from ..db.engine_factory import create_db_engine
from ..db.session import create_session_factory, session_scope
from ..db.types import utc_now
from ..observability.logging_setup import get_logger
from ..repositories import history_repository
from ..services import hourly_aggregation_service

logger = get_logger(__name__)


def add_rebuild_stats_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "rebuild-stats", help="Force-recompute hourly_stats over a date range"
    )
    parser.add_argument(
        "--since", default=None, help="ISO datetime; defaults to the earliest history row"
    )
    parser.add_argument("--until", default=None, help="ISO datetime; defaults to now")
    parser.set_defaults(handler=run_rebuild_stats)


def run_rebuild_stats(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        with session_scope(factory) as session:
            since = _parse(args.since) or history_repository.earliest_change_at(session)
            until = _parse(args.until) or utc_now()
            if since is None:
                logger.info("rebuild_stats_skipped", reason="no history to aggregate")
                return 0
            hours = hourly_aggregation_service.rebuild_hours(session, since=since, until=until)
    finally:
        engine.dispose()

    logger.info("rebuild_stats_completed", hours=hours)
    return 0


def _parse(value: str | None) -> dt.datetime | None:
    if value is None:
        return None
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"'{value}' has no UTC offset; use e.g. 2026-01-01T00:00:00+00:00")
    return parsed
