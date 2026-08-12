"""Starting, restarting and stopping the camera loops."""

from __future__ import annotations

import asyncio
import contextlib
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from ..config.settings import Settings
from ..db.models import Camera
from ..db.session import session_scope
from ..observability.logging_setup import get_logger
from ..realtime.broadcast_hub import BroadcastHub
from ..services import camera_control_service
from .camera_context import CameraContext, build_context
from .camera_loop import run_camera_loop
from .camera_start_stagger import stagger_offsets
from .reload_signals import ReloadSignals

logger = get_logger(__name__)

# Restart backoff after a loop dies unexpectedly. Capped so a camera that is
# broken for hours is retried steadily rather than hammered or abandoned.
INITIAL_BACKOFF_S = 1.0
MAX_BACKOFF_S = 60.0


class CameraSupervisor:
    """Owns one asyncio task per enabled camera."""

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker[Session],
        loop: asyncio.AbstractEventLoop,
        inference_pool: ThreadPoolExecutor,
        db_pool: ThreadPoolExecutor,
        hub: BroadcastHub,
        reload_signals: ReloadSignals,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._loop = loop
        self._inference_pool = inference_pool
        self._db_pool = db_pool
        self._hub = hub
        self._reload_signals = reload_signals

        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._contexts: dict[int, CameraContext] = {}
        self._stop = asyncio.Event()
        self._reconcile_watcher: asyncio.Task[None] | None = None

    # --- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        self._stop.clear()
        await self.reconcile()
        self._reconcile_watcher = self._loop.create_task(
            self._watch_for_reconcile(), name="camera-reconcile-watcher"
        )
        logger.info("camera_supervisor_started", cameras=len(self._tasks))

    async def _watch_for_reconcile(self) -> None:
        """Act on reconcile requests raised while the app is running.

        Without this, `reconcile()` would run exactly once at startup and the
        signal `camera_service` raises after every create, delete or
        enable/disable would sit set and unread - so a camera added from the
        dashboard would never start polling until someone restarted the
        process. Reconciling is idempotent, so a spurious wake-up is harmless.
        """
        event = self._reload_signals.reconcile_event
        while not self._stop.is_set():
            waiter = asyncio.ensure_future(event.wait())
            stopper = asyncio.ensure_future(self._stop.wait())
            try:
                await asyncio.wait({waiter, stopper}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for pending in (waiter, stopper):
                    if not pending.done():
                        pending.cancel()

            if self._stop.is_set():
                return
            if not self._reload_signals.take_reconcile():
                continue
            try:
                await self.reconcile()
                logger.info("camera_supervisor_reconciled", cameras=len(self._tasks))
            except Exception:
                # A broken camera row must not kill the watcher; the next
                # signal has to still be acted on.
                logger.exception("camera_reconcile_failed")

    async def reconcile(self) -> None:
        """Match running tasks to the enabled cameras in the database."""
        enabled = self._enabled_cameras()
        wanted = set(enabled)
        running = set(self._tasks)

        offsets = stagger_offsets(
            wanted - running, fleet_size=len(wanted), poll_interval_s=enabled
        )
        for camera_id, offset_s in offsets.items():
            self._spawn(camera_id, offset_s)
        for camera_id in running - wanted:
            await self._cancel(camera_id)

    async def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()

        watcher, self._reconcile_watcher = self._reconcile_watcher, None
        if watcher is not None:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher

        tasks = list(self._tasks.values())
        if tasks:
            # Give the loops a chance to finish the tick they are on; cancel
            # only the ones that overstay.
            _, pending = await asyncio.wait(tasks, timeout=timeout)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        for context in self._contexts.values():
            context.close()

        self._tasks.clear()
        self._contexts.clear()
        logger.info("camera_supervisor_stopped")

    # --- introspection, for the readiness probe and the operations page ------

    @property
    def running_camera_ids(self) -> list[int]:
        return sorted(self._tasks)

    def context_for(self, camera_id: int) -> CameraContext | None:
        return self._contexts.get(camera_id)

    # --- internals -----------------------------------------------------------

    def _enabled_cameras(self) -> dict[int, float]:
        """Enabled camera ids and their poll intervals, in one query.

        The interval comes back alongside the id rather than in a second
        lookup per camera: staggering needs it, and an N+1 here would run on
        every reconcile, which fires after every camera create, delete or
        enable/disable.
        """
        try:
            with session_scope(self._session_factory) as session:
                return {
                    camera_id: poll_interval_s
                    for camera_id, poll_interval_s in session.execute(
                        select(Camera.id, Camera.poll_interval_s)
                        .where(Camera.is_enabled.is_(True))
                        .order_by(Camera.id)
                    )
                }
        except OperationalError:
            # Almost always a fresh install where migrations have not been run.
            # Serving with no cameras beats refusing to start: the operator can
            # then reach /api/health/ready and read this instruction, whereas a
            # crash loop on a board in a basement tells them nothing.
            logger.error(
                "camera_table_unavailable",
                detail="cannot read the cameras table; run `caps-dash migrate`",
            )
            return {}

    def _spawn(self, camera_id: int, offset_s: float = 0.0) -> None:
        task = self._loop.create_task(
            self._supervise(camera_id, offset_s), name=f"camera-{camera_id}"
        )
        self._tasks[camera_id] = task

    async def _cancel(self, camera_id: int) -> None:
        task = self._tasks.pop(camera_id, None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        context = self._contexts.pop(camera_id, None)
        if context is not None:
            context.close()
        self._reload_signals.forget(camera_id)
        logger.info("camera_stopped", camera_id=camera_id)

    async def _supervise(self, camera_id: int, offset_s: float = 0.0) -> None:
        """Keep one camera's loop alive, backing off between crashes."""
        if offset_s:
            # Once, before the retry loop - never inside it. A camera that
            # crashes and restarts has its own backoff; re-applying the
            # stagger there would make a flapping camera drift further from
            # its slot on every restart.
            await asyncio.sleep(offset_s)

        backoff = INITIAL_BACKOFF_S

        while not self._stop.is_set():
            try:
                context = await asyncio.to_thread(self._build, camera_id)
                self._contexts[camera_id] = context
                backoff = INITIAL_BACKOFF_S  # a clean start resets the penalty

                await self._restore_sensor_settings(context)

                await run_camera_loop(context, self._stop, rebuild=self._rebuild)
                return  # asked to stop

            except asyncio.CancelledError:
                raise
            except Exception:
                # A camera whose configuration is broken, or whose source
                # cannot be constructed, must not take the process with it.
                logger.exception(
                    "camera_loop_crashed", camera_id=camera_id, retry_in_s=backoff
                )
                dead = self._contexts.pop(camera_id, None)
                if dead is not None:
                    dead.close()

                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                    return
                except TimeoutError:
                    backoff = min(backoff * 2, MAX_BACKOFF_S)

    async def _restore_sensor_settings(self, context: CameraContext) -> None:
        """Put the camera's remembered sensor settings back after it restarts.

        The ESP32 keeps them in RAM only, so a power blip silently reverts the
        exposure lock to automatic - and an unlocked sensor hunts, which the
        change gate reads as motion and which takes inference from a small
        fraction of frames to nearly all of them. Nothing would report that;
        the board would just get slower.

        Best effort: a camera that does not answer is already reported through
        its fail-streak, and a brightness value that did not stick must never
        stop the loop from running.
        """
        config = context.config
        if not config.sensor_settings:
            return
        try:
            applied = await camera_control_service.reapply_remembered(
                source_type=config.source_type,
                source_url=config.source_url,
                code=config.code,
                remembered=config.sensor_settings,
                settings=self._settings,
            )
        except Exception:
            logger.warning(
                "sensor_settings_not_restored", camera_id=config.id, exc_info=True
            )
            return
        if applied:
            logger.info("sensor_settings_restored", camera_id=config.id, applied=applied)

    def _build(self, camera_id: int) -> CameraContext:
        return build_context(
            camera_id=camera_id,
            settings=self._settings,
            session_factory=self._session_factory,
            loop=self._loop,
            inference_pool=self._inference_pool,
            db_pool=self._db_pool,
            hub=self._hub,
            reload_signals=self._reload_signals,
        )

    async def _rebuild(self, old: CameraContext) -> CameraContext:
        """Reload configuration mid-flight, with a brand-new vote filter.

        Carrying the old filter over would let a redrawn slot inherit the
        votes of whatever slot previously held its code.
        """
        old.close()
        fresh = await asyncio.to_thread(self._build, old.camera_id)
        # Metrics and the cached still survive a reload - they describe the
        # camera, not the configuration that was just replaced.
        fresh.metrics = old.metrics
        fresh.last_jpeg = old.last_jpeg
        fresh.last_frame_size = old.last_frame_size
        fresh.last_frame_at = old.last_frame_at
        self._contexts[old.camera_id] = fresh
        return fresh
