"""Application lifespan.

Owns everything whose life is longer than one request: the engine, the thread
pools, the broadcast hub and the camera loops. Construction order is the
reverse of teardown order, and both are explicit here rather than scattered
across modules that import each other for side effects.
"""

from __future__ import annotations

import asyncio
import importlib.util
import threading
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from functools import partial

from fastapi import FastAPI

from .app_state import AppState
from .config.settings import Settings
from .db.clock_guard import is_clock_suspect
from .db.engine_factory import create_db_engine
from .db.session import create_session_factory
from .jobs import (
    disk_space_alert_job,
    hourly_aggregation_job,
    overstay_alert_job,
    rate_limiter_sweep_job,
    retention_purge_job,
)
from .jobs.interval_scheduler import JobScheduler, PeriodicJob
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

# Fixed cadences for the phase-13 background jobs. Not settings: unlike the
# business thresholds in `config/settings.py` (overstay hours, disk
# percentage, ...), how OFTEN each job wakes up is an operational wiring
# detail nobody has asked to tune per deployment. `aggregation_interval_s`
# is the one exception - it is a setting because catching up on a stopped
# aggregator is itself tunable work (see `hourly_aggregation_service.py`).
OVERSTAY_INTERVAL_S = 300.0  # 5 min
DISK_SPACE_INTERVAL_S = 900.0  # 15 min
RETENTION_PURGE_INTERVAL_S = 86_400.0  # daily
RATE_LIMITER_SWEEP_INTERVAL_S = 3_600.0  # hourly

# Staggered so five jobs do not all wake in the same second on a board that
# also has to keep every camera loop fed - see `interval_scheduler.py`.
_STAGGER_STEP_S = 20.0


def build_lifespan(settings: Settings) -> Lifespan:
    """Return a lifespan bound to these settings."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state = AppState(settings=settings)
        app.state.caps = state

        state.engine = create_db_engine(settings.database_url)
        # Captured locally, not just read back off `state`: `state.
        # session_factory` is typed `Optional` (phase 01 leaves it `None`
        # before this line runs), and re-reading it below for the job
        # partials would force every call site to re-narrow that `Optional`
        # for no reason - this line is the one place that constructs it.
        session_factory = create_session_factory(state.engine)
        state.session_factory = session_factory

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

        _warn_if_websockets_missing()

        hub = BroadcastHub()
        reload_signals = ReloadSignals(loop)
        supervisor = CameraSupervisor(
            settings=settings,
            session_factory=session_factory,
            loop=loop,
            inference_pool=inference_pool,
            db_pool=db_pool,
            hub=hub,
            reload_signals=reload_signals,
        )

        login_limiter = SlidingWindowLimiter(
            max_attempts=settings.login_max_attempts,
            window_s=settings.login_window_s,
        )
        # Built unconditionally, even when `public_kiosk_enabled` is false: an
        # empty dict and a lock cost nothing, and leaving this `Optional`
        # would force every future call site (Phase 02's public routes) to
        # narrow it before use for a saving that does not exist.
        kiosk_limiter = SlidingWindowLimiter(
            max_attempts=settings.public_kiosk_max_searches,
            window_s=settings.public_kiosk_window_s,
            message="Too many searches from this device. Please wait and try again.",
        )

        state.hub = hub
        state.supervisor = supervisor
        state.services["reload_signals"] = reload_signals
        state.services["inference_pool"] = inference_pool
        state.services["db_pool"] = db_pool
        state.services["login_limiter"] = login_limiter
        state.services["kiosk_limiter"] = kiosk_limiter
        # Backup and purge are rare, heavy, admin-triggered operations; this
        # keeps two from ever running at once (Security Considerations,
        # phase 13). A plain `threading.Lock` is enough - `app.state.caps` is
        # one process, one instance, by design (see `cli/serve_command.py`).
        state.services["system_op_lock"] = threading.Lock()

        job_scheduler = JobScheduler(db_pool=db_pool, loop=loop)
        jobs = [
            PeriodicJob(
                name="hourly_aggregation",
                interval_s=settings.aggregation_interval_s,
                run=partial(hourly_aggregation_job.run, session_factory),
                initial_delay_s=_STAGGER_STEP_S * 0,
            ),
            PeriodicJob(
                name="overstay_alert",
                interval_s=OVERSTAY_INTERVAL_S,
                run=partial(overstay_alert_job.run, session_factory, settings),
                initial_delay_s=_STAGGER_STEP_S * 1,
            ),
            PeriodicJob(
                name="disk_space_alert",
                interval_s=DISK_SPACE_INTERVAL_S,
                run=partial(disk_space_alert_job.run, session_factory, settings),
                initial_delay_s=_STAGGER_STEP_S * 2,
            ),
            PeriodicJob(
                name="retention_purge",
                interval_s=RETENTION_PURGE_INTERVAL_S,
                run=partial(retention_purge_job.run, session_factory, settings),
                initial_delay_s=_STAGGER_STEP_S * 3,
            ),
            PeriodicJob(
                name="rate_limiter_sweep",
                interval_s=RATE_LIMITER_SWEEP_INTERVAL_S,
                run=partial(
                    rate_limiter_sweep_job.run, session_factory, login_limiter, kiosk_limiter
                ),
                initial_delay_s=_STAGGER_STEP_S * 4,
            ),
        ]

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
            public_kiosk_enabled=settings.public_kiosk_enabled,
            # Printed because a wrong value here fails silently everywhere
            # else: every client just looks like the proxy, and "why is every
            # client 127.0.0.1" is the symptom an operator actually sees.
            forwarded_allow_ips=settings.forwarded_allow_ips,
        )

        await supervisor.start()
        job_scheduler.start(jobs)

        try:
            yield
        finally:
            # Reverse order. Stop producing work before tearing down the
            # things that work depends on, or shutdown races itself.
            await job_scheduler.stop()
            await supervisor.stop(timeout=SHUTDOWN_TIMEOUT_S)
            hub.close_all()
            inference_pool.shutdown(wait=True, cancel_futures=True)
            db_pool.shutdown(wait=True)
            if state.engine is not None:
                state.engine.dispose()
            logger.info("shutdown_complete")

    return lifespan


def _warn_if_websockets_missing() -> None:
    """Say at startup that the live view will not work, not on first connect.

    Plain `uvicorn` has no WebSocket implementation; only `uvicorn[standard]`
    pulls one in. Without it every `/ws/...` upgrade is answered with a bare
    404 while the whole REST API keeps working perfectly - so the live view
    looks broken for its own reasons and nobody suspects a missing dependency.
    This happened on a real deployment: the board had a system-wide `uvicorn`
    that satisfied the import, and the extra was never installed.
    """
    if importlib.util.find_spec("websockets") or importlib.util.find_spec("wsproto"):
        return
    logger.error(
        "websocket_library_missing",
        detail=(
            "no websockets/wsproto installed, so /ws/* will answer 404 and the "
            "live camera view cannot connect; install uvicorn[standard]"
        ),
    )


def _safe_db_url(url: str) -> str:
    """Strip any credentials before a URL reaches the log."""
    if "@" not in url:
        return url
    scheme, _, rest = url.partition("://")
    return f"{scheme}://***@{rest.rpartition('@')[2]}"
