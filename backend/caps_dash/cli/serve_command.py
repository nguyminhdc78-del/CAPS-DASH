"""`caps-dash serve`."""

from __future__ import annotations

import argparse
from typing import Any

from ..config.settings import get_settings


def add_serve_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser("serve", help="Run the API and dashboard")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--reload", action="store_true", help="Development autoreload")
    parser.set_defaults(handler=run_serve)


def run_serve(args: argparse.Namespace) -> int:
    import uvicorn

    settings = get_settings()

    # ONE worker, always, and not negotiable. Each worker would start its own
    # camera loop: duplicated requests to every ESP32-CAM, duplicated
    # inference, independent vote filters disagreeing about the same slot, and
    # several processes writing to one SQLite file. The websocket client
    # registry and the login rate limiter are in-process for the same reason.
    #
    # `forwarded_allow_ips` matters now beyond "trust localhost": it decides
    # whether `request.client.host` is the real caller or the reverse proxy,
    # which is what the public-kiosk rate limiter and audit trail key on.
    # Passed explicitly rather than left to uvicorn's own env-var default so
    # the `.env`/`Settings` path (not just a raw `FORWARDED_ALLOW_IPS=` in the
    # shell) actually takes effect for this launch path.
    uvicorn.run(
        "caps_dash.main:app",
        host=args.host or settings.host,
        port=args.port or settings.port,
        reload=args.reload,
        workers=1,
        forwarded_allow_ips=settings.forwarded_allow_ips,
        log_config=None,  # structlog owns logging
    )
    return 0
