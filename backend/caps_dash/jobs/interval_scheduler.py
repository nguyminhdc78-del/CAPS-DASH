"""A small periodic-task scheduler: one asyncio task per job, on its own
interval, cancelled cleanly on shutdown.

Deliberately not a third-party scheduler library. The requirement is "call
this sync function every N seconds, off the event loop, and never let one
job's exception take another down with it" - a handful of lines cover that,
and it is the same shape as `workers/camera_supervisor.py`'s task-per-camera
pattern this codebase already uses.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from ..observability.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass(slots=True, frozen=True)
class PeriodicJob:
    """One background job: what to run, how often, and when to start.

    `initial_delay_s` staggers jobs so they do not all wake in the same
    second the process boots - several jobs competing for the one CPU
    inference also depends on is exactly what staggering avoids.
    """

    name: str
    interval_s: float
    run: Callable[[], None]
    initial_delay_s: float = 0.0


class JobScheduler:
    """Runs each `PeriodicJob.run` on the shared DB executor, on its own
    asyncio task, forever until `stop()`.

    A job's blocking DB work must never run directly on the event loop - see
    `lifespan.py` - so each tick is submitted to `db_pool` and awaited there,
    the same executor the camera worker's writes use.
    """

    def __init__(self, *, db_pool: ThreadPoolExecutor, loop: asyncio.AbstractEventLoop) -> None:
        self._db_pool = db_pool
        self._loop = loop
        self._tasks: list[asyncio.Task[None]] = []
        self._stop = asyncio.Event()

    def start(self, jobs: list[PeriodicJob]) -> None:
        self._stop.clear()
        self._tasks = [
            self._loop.create_task(self._run_forever(job), name=f"job-{job.name}")
            for job in jobs
        ]
        logger.info("job_scheduler_started", jobs=[job.name for job in jobs])

    async def stop(self) -> None:
        self._stop.set()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("job_scheduler_stopped")

    async def _run_forever(self, job: PeriodicJob) -> None:
        if not await self._wait_or_stop(job.initial_delay_s):
            return
        while not self._stop.is_set():
            await self._run_once(job)
            if not await self._wait_or_stop(job.interval_s):
                return

    async def _wait_or_stop(self, timeout: float) -> bool:
        """Sleep for `timeout`, waking early on shutdown. Returns `False`
        when it woke because of shutdown, so the caller can stop looping
        instead of running one more (pointless, near-shutdown) tick.
        """
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=timeout)
            return False
        except TimeoutError:
            return True

    async def _run_once(self, job: PeriodicJob) -> None:
        try:
            await self._loop.run_in_executor(self._db_pool, job.run)
        except asyncio.CancelledError:
            raise
        except Exception:
            # A broken job (a bad threshold, a locked file) must not take
            # every other job down with it, and must not crash the process -
            # scout anti-pattern #11 is exactly a maintenance thread that
            # dies silently on its first unhandled exception.
            logger.exception("job_failed", job=job.name)
