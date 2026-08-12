"""Decisions about whether a tick should do work, separate from doing it.

Split out of `camera_loop.py` to keep that module at the size where the flow
of one tick is readable top to bottom. Both rules here answer "should this
happen now?" and neither touches a frame.
"""

from __future__ import annotations

import time

from ..services.slot_state_service import record_camera_seen
from ..vision.frame_change_gate import GateDecision
from .camera_context import CameraContext

# Status is not history. Writing it every tick would defeat the point of only
# persisting changes.
#
# Measured in seconds, not ticks. Counting ticks ties the write rate to
# `poll_interval_s`, and a camera polled ten times a second - which an RTSP
# source wants, for a smooth picture - then wrote its health to flash every
# two seconds instead of the once a minute that was intended.
HEALTH_INTERVAL_S = 60.0


def too_soon_to_infer(
    decision: GateDecision, last_inference_at: float | None, context: CameraContext
) -> bool:
    """Whether a change-triggered inference should wait for the rate floor.

    Only `changed` is throttled. `first_frame` has no previous result to
    publish instead, and `heartbeat` is precisely the bound on how long the
    system may go on being wrong - throttling either would trade a known limit
    for an unbounded one.

    The change gate's reference frame is deliberately NOT updated when this
    returns True: the scene moved and nothing has looked at it yet, so the
    gate must keep saying "changed" and fire the moment the floor expires.
    """
    minimum = context.settings.min_inference_interval_s
    if minimum <= 0 or last_inference_at is None or decision.reason != "changed":
        return False
    return (time.monotonic() - last_inference_at) < minimum


async def touch_health_if_due(
    context: CameraContext, width: int, height: int, last_at: float | None
) -> float:
    """Record that the camera is alive, at most once a minute.

    Called from BOTH the inference path and the skipped-frame path. Health
    means "frames are arriving", not "the detector ran" - tying it to
    inference made a camera watching a static scene, which is precisely the
    case the change gate exists to skip, look offline while it was working
    perfectly.
    """
    now = time.monotonic()
    if last_at is not None and now - last_at < HEALTH_INTERVAL_S:
        return last_at
    await context.loop.run_in_executor(
        context.db_pool,
        record_camera_seen,
        context.session_factory,
        context.camera_id,
        width,
        height,
    )
    return now
