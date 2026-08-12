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


def needs_more_observations(context: CameraContext) -> bool:
    """Whether the vote filter is still mid-decision and must keep being fed.

    The change gate and the vote filter want opposite things, and this is
    where they are reconciled. The gate skips because "the previous result
    still describes this frame". The filter changes its mind only after
    `threshold` of `window` observations agree. So on the two occasions the
    filter has work to do, the gate is precisely wrong:

    **Warm-up.** A slot reading UNKNOWN has no previous result, so the gate's
    licence does not apply. Measured: two minutes of UNKNOWN after every
    restart or ROI redraw, because a static car park changes nothing and only
    the heartbeat fed the filter - one observation per
    `motion_force_interval_s`, which this migration raised from 10 s to 30 s
    and so tripled.

    **A car arriving or leaving.** Worse, because it looks like a wrong
    answer rather than a missing one. Taking a car out changes the scene
    ONCE: the gate fires, one FREE observation lands, and then the scene is
    static again so the gate skips - leaving the slot reporting OCCUPIED,
    with nothing on screen to explain it, until four heartbeats have passed.
    Reported from the floor: "I took the car out and waited nearly a minute
    and it still says occupied."

    Both are the same condition - the last observation disagrees with the
    reported state - and both cost a handful of extra inferences, once, at
    exactly the moment the answer is in doubt.
    """
    if not context.slot_map.slots:
        # No ROI drawn, so there is no state to settle and nothing this rule
        # can help with. Returning True here was a real fault, not a
        # theoretical one: an unconfigured second camera ran a detection on
        # EVERY tick forever, saturated the single shared inference worker -
        # 2 x 1.5 s of work per 3 s tick - and starved the camera that did
        # have slots. Measured: 11 inferences a minute on the empty camera, 0
        # on the configured one, which is why a slot took a minute to update
        # instead of the twelve seconds the votes actually need.
        return False

    return (
        not context.last_states
        or not context.votes_settled
        or any(str(state) == "UNKNOWN" for state in context.last_states.values())
    )


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
