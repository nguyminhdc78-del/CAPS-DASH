"""Command line entry point.

`caps-dash serve` runs the app. Later phases add `migrate`, `create-admin`,
`backup` and `purge` subcommands here rather than as loose scripts.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from .config.settings import get_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="caps-dash", description="CAPS-DASH administration")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the API and dashboard")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--reload", action="store_true", help="Development autoreload")

    return parser


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    settings = get_settings()
    # ONE worker, always. Multiple workers would run one camera loop per
    # worker: duplicated requests to every ESP32-CAM, duplicated inference,
    # independent vote filters disagreeing about the same slot, and several
    # writers contending for one SQLite file.
    uvicorn.run(
        "caps_dash.main:app",
        host=args.host or settings.host,
        port=args.port or settings.port,
        reload=args.reload,
        workers=1,
        log_config=None,  # structlog owns logging
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        return _serve(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
