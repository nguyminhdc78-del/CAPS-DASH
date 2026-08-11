"""Command line entry point.

Subcommands live in their own modules so this file stays a dispatch table.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from ..config.settings import get_settings
from ..observability.logging_setup import configure_logging
from .backup_command import add_backup_parser
from .create_admin_command import add_create_admin_parser
from .migrate_command import add_migrate_parser
from .purge_command import add_purge_parser
from .rebuild_stats_command import add_rebuild_stats_parser
from .seed_demo_command import add_seed_demo_parser
from .serve_command import add_serve_parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="caps-dash", description="CAPS-DASH administration"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_serve_parser(subparsers)
    add_migrate_parser(subparsers)
    add_create_admin_parser(subparsers)
    add_seed_demo_parser(subparsers)
    add_backup_parser(subparsers)
    add_purge_parser(subparsers)
    add_rebuild_stats_parser(subparsers)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # `serve` hands logging setup to the app factory; everything else is a
    # short-lived command that wants readable console output immediately.
    if args.command != "serve":
        settings = get_settings()
        configure_logging(settings)

    handler = args.handler
    result: int = handler(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
