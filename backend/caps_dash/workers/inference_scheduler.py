"""Runs the detector without the live view waiting for it.

Publishing used to happen *after* the inference await, so every frame a viewer
saw had already aged by one detection before it left the process - ~616 ms on
the board, and N x 616 ms with N cameras queued behind the single shared
inference worker.

That stall landed exactly where it was most visible. An unchanged scene skips
inference altogether, so the picture was smooth while nothing happened and
stuttered the moment a car moved - the only time anybody is watching.

The tick now starts a detection and carries on. Two rules keep that honest:

**At most one detection in flight per camera.** The pool has one worker shared
by every camera, so starting a second would not make it finish sooner; it
would queue a result describing a frame that is already gone, and delay the
one that still matters. A tick that finds the detector busy simply publishes
its frame and moves on.

**A reload discards whatever is running.** `_rebuild` swaps in a new slot map
and a deliberately fresh vote filter. A result computed against the old map
scored against the new one would assign detections to polygons that have since
been redrawn - silently, and with no way to notice afterwards.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable

import numpy as np
from structlog.stdlib import BoundLogger

from .camera_context import CameraContext
from .inference_runner import InferenceOutcome, run_inference

# Scoring a result - fitting the map, voting, persisting changes - is the
# meaning of a tick and stays in `camera_loop`. Passed in as a callback so this
# module owns concurrency only, and so the two do not import each other.
# The frame is handed over too: reading a plate needs the pixels the verdict
# was reached on, and re-deriving them later would read a different moment.
ApplyFn = Callable[[CameraContext, InferenceOutcome, np.ndarray], Awaitable[None]]


class InferenceScheduler:
    """One camera's detector runs, kept off the tick's critical path."""

    __slots__ = ("_generation", "_last_finished_at", "_task")

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._generation = 0
        self._last_finished_at: float | None = None

    @property
    def busy(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def last_finished_at(self) -> float | None:
        """When the last detection completed, for the rate floor.

        Held here rather than on the context so a reload cannot reset it: the
        detector did still run when it ran, whatever the configuration has
        since become.
        """
        return self._last_finished_at

    def invalidate(self) -> None:
        """Drop the result of anything in flight. Called on reload."""
        self._generation += 1

    def start(
        self,
        context: CameraContext,
        image: np.ndarray,
        *,
        apply: ApplyFn,
        log: BoundLogger,
    ) -> None:
        """Begin a detection, unless one is already running."""
        if self.busy:
            return
        self._task = asyncio.create_task(
            self._run(context, image, apply, log, self._generation),
            name=f"inference-{context.camera_id}",
        )

    async def drain(self) -> None:
        """Wait out an in-flight detection at shutdown. Never raises.

        Awaited rather than cancelled: cancelling the task would not stop the
        pool thread that is actually running the model, so the wait happens
        either way - here, where it is visible, or later inside the executor's
        own shutdown. Bounded by one inference.
        """
        task, self._task = self._task, None
        if task is None:
            return
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    async def _run(
        self,
        context: CameraContext,
        image: np.ndarray,
        apply: ApplyFn,
        log: BoundLogger,
        generation: int,
    ) -> None:
        try:
            outcome = await context.loop.run_in_executor(
                context.inference_pool,
                run_inference,
                context.settings,
                image,
                context.config.confidence,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            # Last resort. A model failure on one frame must not kill the task
            # and silently stop the camera forever.
            log.exception("inference_failed")
            context.metrics.record_error("inference failed")
            return

        context.metrics.record_inference(outcome.process_ms)

        if generation != self._generation:
            log.debug("inference_discarded_after_reload")
            return

        self._last_finished_at = time.monotonic()
        # The frame the detector actually saw becomes the gate's reference, so
        # "changed" from here on means changed since this result - not since
        # whatever happened to be on screen when the run was started.
        context.change_gate.mark_inferred(image)
        await apply(context, outcome, image)
