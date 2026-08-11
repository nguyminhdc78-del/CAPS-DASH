"""`caps-dash migrate` - apply database migrations.

An explicit step, never something that happens on import or at app startup.
Automatic migration at boot means an unattended restart can rewrite the schema
of a running system, and on a single-board deployment there is no second
instance to fall back to when that goes wrong.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config

from ..observability.logging_setup import get_logger

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]


def add_migrate_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser("migrate", help="Apply database migrations")
    parser.add_argument(
        "--revision", default="head", help="Target revision (default: head)"
    )
    parser.set_defaults(handler=run_migrate)


def alembic_config() -> Config:
    config_path = REPO_ROOT / "alembic.ini"
    if not config_path.is_file():
        raise FileNotFoundError(f"alembic.ini not found at {config_path}")
    config = Config(str(config_path))
    # Paths in alembic.ini are relative to the repo root, so make sure they
    # resolve no matter which directory the command was run from.
    config.set_main_option(
        "script_location", str(REPO_ROOT / "backend" / "caps_dash" / "db" / "migrations")
    )
    return config


def run_migrate(args: argparse.Namespace) -> int:
    command.upgrade(alembic_config(), args.revision)
    logger.info("migrations_applied", revision=args.revision)
    return 0
