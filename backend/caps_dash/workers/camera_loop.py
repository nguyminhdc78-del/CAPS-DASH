"""One camera's tick loop.

Where each kind of work runs, and why:

  fetching a frame   network I/O, slow, unreliable  -> async, on the event loop
  decode + inference CPU-bound, blocking            -> inference thread pool
  assignment + vote  microseconds of pure Python    -> inline
  writing changes    blocking sqlite3               -> single-thread db pool

Nothing blocking runs on the event loop, so one stalled camera never delays
another, and the API keeps answering while inference is busy.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable

from structlog.stdlib import BoundLogger

from ..observability.logging_setup import get_logger
from ..realtime.frame_protocol import encode_frame_message
from ..services.slot_state_service import persist_state_changes, record_camera_error
from ..vision.domain import count_detections_per_slot, occupied_slot_ids
from .camera_context import CameraContext
from .camera_tick_policy import too_soon_to_infer, touch_health_if_due
from .inference_runner import run_inference

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
    # Local to the loop, not the context: it describes this run of the
    # detector, and a reload that swaps the context must not reset it - the
    # detector did still run when it ran.
    last_inference_at: float | None = None
    last_health_at: float | None = None

    while not stop.is_set() and (max_ticks is None or ticks < max_ticks):
        ticks += 1
        tick_started = time.perf_counter()

        if context.reload_signals.take(context.camera_id):
            context = await rebuild(context)
            log.info("camera_reloaded", slots=len(context.slot_map.slots))

        frame = await asyncio.to_thread(context.source.read)

        if not frame.ok or frame.image is None or frame.jpeg_bytes is None:
            await _handle_failed_read(context, frame.error or "unknown error", log)
            await _sleep_remaining(tick_started, context.config.poll_interval_s, stop)
            continue

        decision = context.change_gate.evaluate(frame.image)

        if not decision.infer or too_soon_to_infer(decision, last_inference_at, context):
            # The picture has not changed since the detector last looked, so
            # the previous result still describes it. Publishing that result
            # with this frame is honest - they are the same scene - and the
            # vote filter is deliberately NOT updated: a repeated frame is not
            # new evidence, and feeding it in would let one stale observation
            # vote itself into a majority.
            seq += 1
            _publish_unchanged(context, frame.jpeg_bytes, seq)
            context.metrics.record_success(
                process_ms=0.0, tick_ms=(time.perf_counter() - tick_started) * 1000.0
            )
            # A frame arrived, so the camera is alive - whether or not the
            # detector chose to look at it.
            width, height = context.last_frame_size
            last_health_at = await touch_health_if_due(context, width, height, last_health_at)
            await _sleep_remaining(tick_started, context.config.poll_interval_s, stop)
            continue

        try:
            outcome = await context.loop.run_in_executor(
                context.inference_pool,
                run_inference,
                context.settings,
                frame.image,
                context.config.confidence,
            )
        except Exception:
            # Last resort. A model failure on one frame must not kill the task
            # and silently stop the camera forever.
            log.exception("inference_failed")
            context.metrics.record_error("inference failed")
            await _sleep_remaining(tick_started, context.config.poll_interval_s, stop)
            continue

        context.change_gate.mark_inferred(frame.image)
        last_inference_at = time.monotonic()
        log.debug("inference_ran", reason=decision.reason, difference=round(decision.difference, 2))

        fitted = context.slot_map.fit_to_frame(outcome.frame_w, outcome.frame_h)
        states = context.vote_filter.update(occupied_slot_ids(outcome.detections, fitted))
        context.remember_result(outcome, states, fitted)

        changes = context.state_tracker.diff(states)
        if changes:
            await context.loop.run_in_executor(
                context.db_pool,
                persist_state_changes,
                context.session_factory,
                context.camera_id,
                changes,
            )
            log.info("slot_states_changed", changes=len(changes))

        overlapping = [
            code
            for code, count in count_detections_per_slot(outcome.detections, fitted).items()
            if count >= 2
        ]
        if overlapping:
            # Two vehicles in one slot means the polygon reaches into the row
            # behind it - a drawing mistake worth catching at install time.
            log.warning("slot_matched_multiple_vehicles", slots=overlapping)

        tick_ms = (time.perf_counter() - tick_started) * 1000.0
        context.metrics.record_success(process_ms=outcome.process_ms, tick_ms=tick_ms)
        context.remember_frame(frame.jpeg_bytes, outcome.frame_w, outcome.frame_h)

        seq += 1
        if context.hub.has_viewers(context.camera_id):
            # Only encode and publish when somebody is watching. The bytes are
            # the camera's own JPEG, passed through untouched.
            context.hub.publish(
                context.camera_id,
                encode_frame_message(
                    context.build_header(outcome, states, seq, fitted), frame.jpeg_bytes
                ),
            )

        last_health_at = await touch_health_if_due(
            context, outcome.frame_w, outcome.frame_h, last_health_at
        )

        await _sleep_remaining(tick_started, context.config.poll_interval_s, stop)


def _publish_unchanged(context: CameraContext, jpeg: bytes, seq: int) -> None:
    """Send a skipped frame to viewers, described by the last real inference.

    The live view must stay smooth even when the detector is idle - that is
    the whole point of skipping - so the frame still goes out, carrying the
    boxes and states from the last frame the detector saw. Nothing is
    fabricated: the scene is unchanged, so those results still describe it.
    """
    context.remember_frame(jpeg, *context.last_frame_size)

    outcome, fitted = context.last_outcome, context.last_fitted
    if outcome is None or fitted is None or not context.hub.has_viewers(context.camera_id):
        return

    header = context.build_header(outcome, context.last_states, seq, fitted)
    header["inference_skipped"] = True
    context.hub.publish(context.camera_id, encode_frame_message(header, jpeg))


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
