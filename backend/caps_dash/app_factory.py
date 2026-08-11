"""Application assembly.

Assembly only - no business logic, no route bodies. Everything this function
touches is defined elsewhere, which keeps the startup order readable at a
glance. Order is load-bearing and commented where it is not obvious.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api.router import api_router
from .config.settings import Settings
from .errors.handlers import register_exception_handlers
from .lifespan import build_lifespan
from .observability.logging_setup import configure_logging
from .observability.request_id_middleware import RequestIdMiddleware
from .web.spa_static import mount_spa

DESCRIPTION = """\
Car-park administration for the CAPS system.

All vehicle detection runs on this host; camera images never leave the
building. Residents see counts only - which slot holds which car is private.
"""


def create_app(settings: Settings) -> FastAPI:
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

    # LAST. A static mount at "/" matches everything that reaches it.
    mount_spa(app, settings)

    return app
