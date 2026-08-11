"""`caps-dash purge` - retention purge outside the running API.

`--dry-run` (the default) previews counts without deleting; `--execute` is
required to actually delete, so a bare `caps-dash purge` at a terminal never
destroys data by accident - the same "safe by default" choice as
`PurgeRequest.dry_run` on the HTTP endpoint.
"""

from __future__ import annotations

import argparse
from typing import Any

from ..config.settings import get_settings
from ..db.engine_factory import create_db_engine
from ..db.session import create_session_factory, session_scope
from ..observability.logging_setup import get_logger
from ..services import retention_service

logger = get_logger(__name__)

CLI_ACTOR_USERNAME = "cli"


def add_purge_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser("purge", help="Purge data past the retention window")
    parser.add_argument(
        "--older-than-months",
        type=int,
        default=None,
        help="Override settings.retention_months for this run",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete. Without this flag the command only previews counts.",
    )
    parser.set_defaults(handler=run_purge)


def run_purge(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        with session_scope(factory) as session:
            result = retention_service.purge(
                session,
                settings=settings,
                older_than_months=args.older_than_months,
                dry_run=not args.execute,
                actor_username=CLI_ACTOR_USERNAME,
            )
    finally:
        engine.dispose()

    logger.info(
        "purge_ran",
        dry_run=not args.execute,
        deleted_history_rows=result.deleted_history_rows,
        deleted_alert_rows=result.deleted_alert_rows,
    )
    return 0
