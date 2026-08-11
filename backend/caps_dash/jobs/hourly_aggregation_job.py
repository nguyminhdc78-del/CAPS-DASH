"""Periodic job: roll closed hours of `slot_state_history` into `hourly_stats`.

Registered on the scheduler in `lifespan.py`, every `settings.
aggregation_interval_s` (10 minutes by default) - short enough that a chart
is never far behind, incremental so a normal tick costs at most one or two
hours of work.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from ..db.session import session_scope
from ..observability.logging_setup import get_logger
from ..services import hourly_aggregation_service

logger = get_logger(__name__)


def run(factory: sessionmaker[Session]) -> None:
    with session_scope(factory) as session:
        processed = hourly_aggregation_service.aggregate_pending_hours(session)
    if processed:
        logger.info("hourly_aggregation_job_ran", hours_processed=processed)
