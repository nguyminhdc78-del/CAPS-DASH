"""`caps-dash backup` - take a database backup outside the running API.

Useful before a manual maintenance step (a migration, a disk swap) when
nobody wants to authenticate to `/system/backup` first. Uses the same
`backup_service.create_backup_and_audit` the API route calls, so the two
paths can never silently diverge in behaviour.
"""

from __future__ import annotations

import argparse
from typing import Any

from ..config.settings import get_settings
from ..db.engine_factory import create_db_engine
from ..db.session import create_session_factory
from ..observability.logging_setup import get_logger
from ..services import backup_service

logger = get_logger(__name__)

CLI_ACTOR_USERNAME = "cli"


def add_backup_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser("backup", help="Take a database backup")
    parser.set_defaults(handler=run_backup)


def run_backup(args: argparse.Namespace) -> int:
    del args
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        result = backup_service.create_backup_and_audit(
            engine, factory, settings, actor_username=CLI_ACTOR_USERNAME
        )
    finally:
        engine.dispose()

    logger.info("backup_created", path=result.backup_path, size_bytes=result.size_bytes)
    return 0
