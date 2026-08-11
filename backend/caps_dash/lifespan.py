"""Application lifespan.

Owns the construction and teardown of everything with a lifetime longer than
one request. Phase 01 establishes the shape; phases 02 and 06 fill it in.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from .app_state import AppState
from .config.settings import Settings
from .db.clock_guard import is_clock_suspect
from .db.engine_factory import create_db_engine
from .db.session import create_session_factory
from .observability.logging_setup import get_logger
from .security.rate_limiter import SlidingWindowLimiter

logger = get_logger(__name__)

# What `asynccontextmanager` actually produces: a factory returning a context
# manager, not the async generator itself.
Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def build_lifespan(settings: Settings) -> Lifespan:
    """Return a lifespan bound to these settings."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state = AppState(settings=settings)
        app.state.caps = state

        state.engine = create_db_engine(settings.database_url)
        state.session_factory = create_session_factory(state.engine)

        # In-process, which is correct rather than a shortcut: one uvicorn
        # worker by design, so there is no second process to share counters
        # with. See the CLI for why the worker count is fixed.
        state.services["login_limiter"] = SlidingWindowLimiter(
            max_attempts=settings.login_max_attempts,
            window_s=settings.login_window_s,
        )

        if is_clock_suspect():
            # Say so loudly rather than let every timestamped row be quietly
            # wrong. The board has no RTC battery; rows written before NTP
            # catches up are flagged and reports exclude them.
            logger.warning(
                "clock_suspect",
                detail="system clock is implausible; time-stamped rows will be flagged",
            )

        logger.info(
            "startup",
            app_env=settings.app_env,
            database_url=_safe_db_url(settings.database_url),
            detector_backend=settings.detector_backend,
        )

        try:
            yield
        finally:
            # Teardown runs in reverse order of construction. Later phases add
            # worker shutdown and executor drain here, before the engine closes.
            if state.engine is not None:
                state.engine.dispose()
            logger.info("shutdown_complete")

    return lifespan


def _safe_db_url(url: str) -> str:
    """Strip any credentials before a URL reaches the log."""
    if "@" not in url:
        return url
    scheme, _, rest = url.partition("://")
    return f"{scheme}://***@{rest.rpartition('@')[2]}"
