"""Getting one frame to whoever is watching.

Split out of `camera_loop` because it answers a question of its own - what
does a viewer see, and how current is it - and because that question is the
whole reason the loop is shaped the way it is.

The rule: **the picture never waits for the detector.** Publishing used to sit
behind the inference await, so every frame a viewer saw had already aged by a
whole detection. The boxes drawn over it may lag; the picture may not.
"""

from __future__ import annotations

from ..realtime.frame_protocol import encode_frame_message
from .camera_context import CameraContext
from .inference_runner import InferenceOutcome


def publish_frame(
    context: CameraContext,
    jpeg: bytes,
    width: int,
    height: int,
    seq: int,
    last_published: InferenceOutcome | None,
) -> InferenceOutcome | None:
    """Send the frame to viewers now, described by the last completed detection.

    The boxes trail the picture by at most one detection - marked in the
    header as `inference_skipped` - and the slot states they carry are
    vote-filtered over several frames anyway, so they were never
    instantaneous. Nothing is fabricated: the header says plainly whether the
    detector looked at this frame or at an earlier one.

    Returns whichever result was sent, for the next frame to compare against.
    """
    context.remember_frame(jpeg, width, height)

    outcome, fitted = context.last_outcome, context.last_fitted
    if outcome is None or fitted is None:
        return last_published  # the first detection is still running
    if not context.hub.has_viewers(context.camera_id):
        return last_published  # encoding a message with no destination is waste

    # Polygons are fitted to the frame the detector saw. If the camera changes
    # resolution mid-stream that is briefly not this frame, and the overlay is
    # off until the next result lands - one detection, self-correcting.
    header = context.build_header(outcome, context.last_states, seq, fitted)
    header["inference_skipped"] = outcome is last_published
    context.hub.publish(context.camera_id, encode_frame_message(header, jpeg))
    return outcome
