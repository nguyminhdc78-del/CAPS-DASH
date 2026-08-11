"""Periodic job: purge `slot_state_history`/acknowledged `alerts` past
`settings.retention_months`.

Registered on the scheduler once a day. Always a real purge (never dry-run -
dry-run is a manual preview action, exposed only through `POST /system/purge`
and the CLI's `--dry-run` flag) and always audited, same as the manual path,
via the shared `retention_service.purge`.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from ..config.settings import Settings
from ..db.session import session_scope
from ..observability.logging_setup import get_logger
from ..services import retention_service

logger = get_logger(__name__)

# Distinguishes job-triggered audit rows from an admin's own click without
# needing a real `User` row - there is no user in scope on a background tick.
JOB_ACTOR_USERNAME = "scheduler"


def run(factory: sessionmaker[Session], settings: Settings) -> None:
    with session_scope(factory) as session:
        result = retention_service.purge(
            session,
            settings=settings,
            older_than_months=None,
            dry_run=False,
            actor_username=JOB_ACTOR_USERNAME,
        )
    logger.info(
        "retention_purge_job_ran",
        deleted_history_rows=result.deleted_history_rows,
        deleted_alert_rows=result.deleted_alert_rows,
    )
