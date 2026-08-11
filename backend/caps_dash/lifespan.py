"""Application lifespan.

Owns everything whose life is longer than one request: the engine, the thread
pools, the broadcast hub and the camera loops. Construction order is the
reverse of teardown order, and both are explicit here rather than scattered
across modules that import each other for side effects.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from .app_state import AppState
from .config.settings import Settings
from .db.clock_guard import is_clock_suspect
from .db.engine_factory import create_db_engine
from .db.session import create_session_factory
from .observability.logging_setup import get_logger
from .realtime.broadcast_hub import BroadcastHub
from .security.rate_limiter import SlidingWindowLimiter
from .workers.camera_supervisor import CameraSupervisor
from .workers.reload_signals import ReloadSignals

logger = get_logger(__name__)

# What `asynccontextmanager` actually produces: a factory returning a context
# manager, not the async generator itself.
Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]

SHUTDOWN_TIMEOUT_S = 10.0


def build_lifespan(settings: Settings) -> Lifespan:
    """Return a lifespan bound to these settings."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state = AppState(settings=settings)
        app.state.caps = state

        state.engine = create_db_engine(settings.database_url)
        state.session_factory = create_session_factory(state.engine)

        loop = asyncio.get_running_loop()

        # Inference is CPU-bound and blocking, so it never touches the event
        # loop. One worker by default: one model in memory, and serialised
        # inference is the right shape for the board this runs on.
        inference_pool = ThreadPoolExecutor(
            max_workers=settings.inference_pool_size, thread_name_prefix="infer"
        )
        # Exactly one writer. SQLite permits one anyway; funnelling through a
        # single thread makes contention structurally impossible instead of
        # something busy_timeout has to keep absorbing.
        db_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dbwrite")

        hub = BroadcastHub()
        reload_signals = ReloadSignals(loop)
        supervisor = CameraSupervisor(
            settings=settings,
            session_factory=state.session_factory,
            loop=loop,
            inference_pool=inference_pool,
            db_pool=db_pool,
            hub=hub,
            reload_signals=reload_signals,
        )

        state.hub = hub
        state.supervisor = supervisor
        state.services["reload_signals"] = reload_signals
        state.services["inference_pool"] = inference_pool
        state.services["db_pool"] = db_pool
        state.services["login_limiter"] = SlidingWindowLimiter(
            max_attempts=settings.login_max_attempts,
            window_s=settings.login_window_s,
        )

        if is_clock_suspect():
            # Said out loud rather than letting every timestamped row be
            # quietly wrong. The board has no RTC battery; rows written before
            # NTP catches up are flagged and reports exclude them.
            logger.warning(
                "clock_suspect",
                detail="system clock is implausible; time-stamped rows will be flagged",
            )

        logger.info(
            "startup",
            app_env=settings.app_env,
            database_url=_safe_db_url(settings.database_url),
            detector_backend=settings.detector_backend,
            inference_workers=settings.inference_pool_size,
        )

        await supervisor.start()

        try:
            yield
        finally:
            # Reverse order. Stop producing work before tearing down the
            # things that work depends on, or shutdown races itself.
            await supervisor.stop(timeout=SHUTDOWN_TIMEOUT_S)
            hub.close_all()
            inference_pool.shutdown(wait=True, cancel_futures=True)
            db_pool.shutdown(wait=True)
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
