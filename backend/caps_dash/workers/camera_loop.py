"""One camera's tick loop.

Where each kind of work runs, and why:

  fetching a frame   network I/O, slow, unreliable  -> async, on the event loop
  decode + inference CPU-bound, blocking            -> inference thread pool
  assignment + vote  microseconds of pure Python    -> inline
  writing changes    blocking sqlite3               -> single-thread db pool

Nothing blocking runs on the event loop, so one stalled camera never delays
another, and the API keeps answering while inference is busy.

A tick does two things: publish the frame it has just read, and decide whether
to *start* a detection. It never waits for one. Publishing behind the
inference await put a whole detection - ~616 ms on the board, more with
cameras queued behind the single shared worker - into the age of every frame a
viewer saw, and only on the ticks where the picture had changed. The live view
was smooth while nothing happened and stuttered the moment a car moved. See
`inference_scheduler`.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace

import numpy as np
from structlog.stdlib import BoundLogger

from ..observability.logging_setup import get_logger
from ..services.slot_state_service import record_camera_error
from .camera_context import CameraContext
from .camera_tick_policy import needs_more_observations, too_soon_to_infer, touch_health_if_due
from .frame_publisher import publish_frame
from .inference_outcome_applier import apply_outcome
from .inference_runner import InferenceOutcome
from .inference_scheduler import InferenceScheduler

logger = get_logger(__name__)

# Rebuilding a context needs the supervisor's wiring, so the loop takes it as
# a callback rather than importing the supervisor and creating a cycle.
RebuildFn = Callable[[CameraContext], Awaitable[CameraContext]]


async def run_camera_loop(
    context: CameraContext,
    stop: asyncio.Event,
    *,
    rebuild: RebuildFn,
    max_ticks: int | None = None,
) -> None:
    """Poll one camera until told to stop.

    `max_ticks` exists so tests can run a bounded number of iterations; in
    production it is None and the loop runs until shutdown.
    """
    log = logger.bind(camera_id=context.camera_id, camera_code=context.config.code)
    seq = 0
    ticks = 0
    last_health_at: float | None = None
    last_jpeg: bytes | None = None
    # The result the viewers were last sent, so a republished one can be
    # marked as such.
    published: InferenceOutcome | None = None
    # Local to the loop, not the context: a reload swaps the context out, and
    # what the detector has already done must survive that.
    scheduler = InferenceScheduler()

    try:
        while not stop.is_set() and (max_ticks is None or ticks < max_ticks):
            ticks += 1
            tick_started = time.perf_counter()

            if context.reload_signals.take(context.camera_id):
                context = await rebuild(context)
                scheduler.invalidate()
                published = None
                log.info("camera_reloaded", slots=len(context.slot_map.slots))

            frame = await asyncio.to_thread(context.source.read)

            if not frame.ok or frame.image is None or frame.jpeg_bytes is None:
                await _handle_failed_read(context, frame.error or "unknown error", log)
                await _sleep_remaining(tick_started, context.config.poll_interval_s, stop)
                continue

            if frame.jpeg_bytes is last_jpeg:
                # Literally the same object the source handed over last tick, so
                # the camera has not produced anything since. A source that
                # refreshes every few seconds against a worker ticking ten times
                # a second would otherwise re-run the change gate and push
                # identical bytes to every viewer thirty times over - CPU and
                # WiFi spent carrying no new information. Sources that build a
                # fresh frame per read never take this branch.
                await _sleep_remaining(tick_started, context.config.poll_interval_s, stop)
                continue
            last_jpeg = frame.jpeg_bytes

            height, width = frame.image.shape[:2]
            seq += 1
            published = publish_frame(
                context, frame.jpeg_bytes, width, height, seq, published
            )

            context.metrics.record_success(
                tick_ms=(time.perf_counter() - tick_started) * 1000.0
            )
            # A frame arrived, so the camera is alive - whether or not the
            # detector chose to look at it.
            last_health_at = await touch_health_if_due(context, width, height, last_health_at)

            _maybe_infer(context, frame.image, scheduler, log)

            # Driven from the tick, NOT from `apply_outcome`, and that is the
            # whole point. A detection only happens when the change gate lets
            # one through, so on a quiet car park - nothing moving, votes long
            # settled - inference stops, and with it went every ring push: the
            # lamp fell past the firmware's 90 s staleness window and showed
            # "no server" amber over bays whose state was perfectly well known.
            # Measured on the board before this moved: 321 s without a push.
            # The states are known every tick, so they are sent every tick and
            # `SlotLedRing` throttles them down to a change or a 15 s refresh.
            await context.led_ring.push(
                source_type=context.config.source_type,
                source_url=context.config.source_url,
                code=context.config.code,
                states=context.last_states,
            )

            await _sleep_remaining(tick_started, context.config.poll_interval_s, stop)
    finally:
        await scheduler.drain()


def _maybe_infer(
    context: CameraContext,
    image: np.ndarray,
    scheduler: InferenceScheduler,
    log: BoundLogger,
) -> None:
    """Start a detection if the scene warrants one and the detector is free."""
    if scheduler.busy:
        # Checked before the change gate, not after: with the detector already
        # running the answer cannot be acted on, so the comparison would be
        # 2.7 ms of a tick spent deciding nothing.
        return

    decision = context.change_gate.evaluate(image)
    if not decision.infer and needs_more_observations(context):
        # Skipping now would starve the vote filter of the observations it is
        # waiting on, and the slot would keep reporting the old answer - see
        # `needs_more_observations`.
        decision = replace(decision, infer=True, reason="settling")

    if not decision.infer or too_soon_to_infer(decision, scheduler.last_finished_at, context):
        # The picture has not changed since the detector last looked, so the
        # previous result still describes it - which is exactly what viewers
        # are already being sent. The vote filter is deliberately NOT updated:
        # a repeated frame is not new evidence, and feeding it in would let one
        # stale observation vote itself into a majority.
        return

    log.debug("inference_started", reason=decision.reason, difference=round(decision.difference, 2))
    scheduler.start(context, image, apply=apply_outcome, log=log)


async def _handle_failed_read(
    context: CameraContext, error: str, log: BoundLogger
) -> None:
    context.metrics.record_failure(error)
    threshold = context.settings.camera_fail_streak_offline

    if context.metrics.fail_streak == threshold:
        # Logged once, on the transition. Repeating it every tick for a camera
        # that is unplugged for a week buries everything else.
        log.warning("camera_offline", error=error, fail_streak=threshold)
        await context.loop.run_in_executor(
            context.db_pool,
            record_camera_error,
            context.session_factory,
            context.camera_id,
            error,
        )


async def _sleep_remaining(started: float, interval_s: float, stop: asyncio.Event) -> None:
    """Sleep out the rest of the tick, waking early if asked to stop.

    Measured from the start of the tick so the poll rate stays steady rather
    than drifting by however long the work took.
    """
    remaining = interval_s - (time.perf_counter() - started)
    if remaining <= 0:
        return
    # TimeoutError here just means the full interval elapsed, which is the
    # normal path; a stop request simply wakes us early.
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=remaining)
