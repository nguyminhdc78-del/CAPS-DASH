"""Application assembly.

Assembly only - no business logic, no route bodies. Everything this function
touches is defined elsewhere, which keeps the startup order readable at a
glance. Order is load-bearing and commented where it is not obvious.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api.router import api_router
from .config.settings import Settings
from .errors.handlers import register_exception_handlers
from .lifespan import build_lifespan
from .observability.logging_setup import configure_logging
from .observability.request_id_middleware import RequestIdMiddleware
from .realtime.ws_routes import router as ws_router
from .web.spa_static import mount_spa

DESCRIPTION = """\
Car-park administration for the CAPS system.

All vehicle detection runs on this host; camera images never leave the
building.

**Authenticated API** (`/api`): Residents see occupancy counts only (which slot
holds which car is private). Security staff can search by licence plate. Admin
can manage cameras and ROI.

**Public Kiosk** (`/api/public`, gated by `PUBLIC_KIOSK_ENABLED`): Shows free
bay codes and (when `PLATE_READING_ENABLED=true`) allows partial-match
licence-plate search for customers to find their own car. This is a deliberate
privacy trade-off - anyone on the network can enumerate the car park and
locate a vehicle. Mitigated by: kill-switch (default off), per-IP rate limit,
and anonymous audit. See `docs/project-overview-pdr.md` Privacy Position.
"""


def _reject_multiple_workers() -> None:
    """Refuse to start under more than one uvicorn worker.

    This is a correctness constraint, not a tuning knob: each worker starts
    its own `CameraSupervisor`, so N workers means N duplicate polls of every
    ESP32-CAM, N inference runs per frame, N independently-warmed vote filters
    that can disagree about the same slot, and N processes racing to be "the"
    writer on one SQLite file (which the app otherwise guarantees by funnelling
    every write through a single thread - see `lifespan.py`). `caps-dash serve`
    and the shipped Dockerfile/systemd unit already hard-code `--workers 1`;
    this is the last line of defence for anyone who launches uvicorn directly.

    `WEB_CONCURRENCY` is the variable to check because it is exactly what
    uvicorn's own `--workers` flag defaults to when the flag itself is not
    passed (see `uvicorn --help`: "Defaults to the $WEB_CONCURRENCY
    environment variable"), which makes it the one signal available inside the
    ASGI app process itself - uvicorn's multiprocess supervisor does not
    otherwise tell a worker process how many siblings it has.
    """
    raw = os.environ.get("WEB_CONCURRENCY", "").strip()
    if not raw:
        return
    try:
        workers = int(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"WEB_CONCURRENCY={raw!r} is not an integer; refusing to start rather "
            "than guess how many workers that means."
        ) from exc
    if workers > 1:
        raise RuntimeError(
            f"WEB_CONCURRENCY={workers} requests multiple worker processes, which "
            "CAPS-DASH refuses to run: each worker would start its own camera "
            "loop, duplicating requests to every camera and racing to write the "
            "same SQLite file. Run exactly one worker (--workers 1)."
        )


def create_app(settings: Settings) -> FastAPI:
    _reject_multiple_workers()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version=__version__,
        lifespan=build_lifespan(settings),
        docs_url=None if settings.is_prod else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_prod else "/openapi.json",
    )

    # Middleware is applied bottom-up, so the request id is bound first and
    # remains available to everything above it, including CORS rejections.
    #
    # Deliberately NOT adding uvicorn's `ProxyHeadersMiddleware` here. uvicorn
    # already wraps the whole ASGI app in one copy of it whenever
    # `proxy_headers=True` (the default) - see `Config.load()` - using
    # `forwarded_allow_ips`/`FORWARDED_ALLOW_IPS`. A second copy inside
    # `create_app` would sit *inside* that one, see a `scope["client"]` the
    # outer copy already rewrote, and double-apply the trust decision. The fix
    # for "the real client IP is wrong" is `Settings.forwarded_allow_ips`
    # (`config/settings.py`), not another middleware here.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestIdMiddleware)

    register_exception_handlers(app)

    # Real routes, then the /api catch-all inside api_router, then the SPA.
    app.include_router(api_router, prefix="/api")
    app.include_router(ws_router, prefix="/ws")

    # LAST. A static mount at "/" matches everything that reaches it.
    mount_spa(app, settings)

    return app
