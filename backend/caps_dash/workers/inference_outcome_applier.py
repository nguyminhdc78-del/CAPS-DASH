"""Turning one detection result into slot state.

Split out of `camera_loop` because it no longer happens *in* a tick. The
detector runs on its own, and whenever a result lands - possibly several ticks
after the frame it describes was read - this is what is done with it.

Everything here is about a result, nothing about a frame or a schedule, which
is what makes it worth its own module rather than a branch in the loop.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from ..observability.logging_setup import get_logger
from ..services.slot_state_service import persist_state_changes
from ..vision.domain import SlotState, count_detections_per_slot, resolve_slot_detections
from .camera_context import CameraContext
from .inference_runner import InferenceOutcome
from .plate_capture import read_plates_for_filled_slots

logger = get_logger(__name__)


async def apply_outcome(
    context: CameraContext, outcome: InferenceOutcome, image: np.ndarray
) -> None:
    """Vote on one detection, persist what changed, keep it for the live view."""
    log = logger.bind(camera_id=context.camera_id, camera_code=context.config.code)

    fitted = context.slot_map.fit_to_frame(outcome.frame_w, outcome.frame_h)

    # One vehicle per slot, nothing outside a slot. Everything below - state,
    # the live overlay, the plate reader - works from this rather than from the
    # detector's raw output. The raw list is kept only for the install-time
    # check further down, which is the one question that needs to know what was
    # thrown away.
    resolved = resolve_slot_detections(outcome.detections, fitted)
    occupied_now = set(resolved)
    states = context.vote_filter.update(occupied_now)

    # Viewers see the resolved boxes, not the raw ones. A detector run near its
    # confidence floor - which is where a stock COCO model has to sit to see a
    # car at all under this camera - paints the picture with boxes over
    # whatever else is in shot, and the operator cannot tell those from the
    # cars. Publishing what was actually reasoned about is both quieter and
    # more honest: the overlay now matches the state beside it.
    context.remember_result(
        replace(outcome, detections=list(resolved.values())), states, fitted
    )

    # Does what the detector just saw agree with what the filter is reporting?
    # A disagreement means a slot is mid-transition - the car has gone but the
    # vote has not carried yet - and the loop must keep looking until it
    # settles. The raw observation used to be computed here and discarded,
    # which is why a slot could sit on OCCUPIED for two minutes after the car
    # left: the scene went static again, the change gate skipped every tick,
    # and the votes needed to flip it never arrived.
    disagreeing = _disagreeing_slots(occupied_now, states)
    context.votes_settled = not disagreeing

    if disagreeing:
        # The one line that makes "why is it still saying occupied?" answerable
        # without instrumenting a running board: what the detector saw, what
        # the filter is reporting, and which slots are between the two.
        log.debug(
            "votes_settling",
            seen_occupied=sorted(occupied_now),
            reporting={code: str(state) for code, state in states.items()},
            disagreeing=disagreeing,
        )

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
        await read_plates_for_filled_slots(context, changes, image, fitted, log)

    overlapping = [
        code
        for code, count in count_detections_per_slot(outcome.detections, fitted).items()
        if count >= 2
    ]
    if overlapping:
        # Two vehicles in one slot means the polygon reaches into the row
        # behind it - a drawing mistake worth catching at install time.
        log.warning("slot_matched_multiple_vehicles", slots=overlapping)


def _disagreeing_slots(occupied_now: set[str], states: dict[str, SlotState]) -> list[str]:
    """Slots whose latest observation contradicts their reported state.

    UNKNOWN counts as disagreement whatever was seen: the filter has no
    verdict yet, so it needs observations regardless of which way they point.
    """
    return [
        code
        for code, state in states.items()
        if state is SlotState.UNKNOWN or (code in occupied_now) != (state is SlotState.OCCUPIED)
    ]
