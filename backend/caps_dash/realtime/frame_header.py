"""The JSON half of a realtime message.

Separate from the codec so the codec knows nothing about slots, detections or
inference, and separate from the worker so this module can be tested without an
event loop or a camera.

Polygons here are already **fitted to the live frame**, so a client can draw
them straight onto the image it just received. `frame_w`/`frame_h` are included
as well, because the browser still has to scale from frame pixels to whatever
size the canvas happens to be. The ROI editor is the exception and keeps
working in source pixels - it is editing the stored map, not this frame.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a worker->realtime cycle
    from ..vision.domain import SlotMap
    from ..workers.inference_runner import InferenceOutcome

# Coordinates are rounded to a tenth of a pixel. Full float repr would roughly
# double the header for precision no display can show.
COORD_DIGITS = 1

# A header past this is a bug (a site-wide map on one camera, say), not a
# legitimate frame. Logged rather than raised - dropping the frame would hide
# the problem, and the codec's own hard limit still applies.
HEADER_WARN_BYTES = 8 * 1024


def build_frame_header(
    *,
    camera_id: int,
    camera_code: str,
    seq: int,
    outcome: InferenceOutcome,
    states: Mapping[str, Any],
    fitted: SlotMap,
    captured_at: dt.datetime | None = None,
) -> dict[str, Any]:
    """Describe one tick: what the frame is, and what was found in it."""
    moment = captured_at or dt.datetime.now(dt.UTC)
    return {
        "camera_id": camera_id,
        "camera_code": camera_code,
        "seq": seq,
        "captured_at": moment.isoformat(),
        "frame_w": outcome.frame_w,
        "frame_h": outcome.frame_h,
        "process_ms": round(outcome.process_ms, 1),
        "confidence": round(outcome.confidence, 3),
        "slots": [
            {
                "code": slot.id,
                "state": str(states.get(slot.id, slot.state)),
                "polygon": [
                    [round(x, COORD_DIGITS), round(y, COORD_DIGITS)] for x, y in slot.polygon
                ],
            }
            for slot in fitted.slots
        ],
        "detections": [
            {
                "x1": round(detection.x1, COORD_DIGITS),
                "y1": round(detection.y1, COORD_DIGITS),
                "x2": round(detection.x2, COORD_DIGITS),
                "y2": round(detection.y2, COORD_DIGITS),
                "confidence": round(detection.confidence, 3),
                "label": detection.label,
            }
            for detection in outcome.detections
        ],
    }
