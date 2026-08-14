"""Reducing a frame's worth of detections to one vehicle per slot.

`assignment` answers "which slot is THIS box in". This module answers the
question the rest of the system actually asks: given everything the detector
returned for one frame, what is in each bay?

Two rules, and both exist because a stock COCO model pointed at a car park is
a noisy instrument:

1. **The ROI is the filter.** A box outside every slot is discarded. The
   detector reports whatever is in shot, and a car park camera sees floors,
   chairs, bags and passers-by; none of it is evidence about a bay. On the
   reference rig a computer mouse on the desk behind the bays scored as a car
   on most frames.

2. **A bay holds one vehicle.** Extra boxes in the same slot are that same car
   described again - as another class, or at another scale - so the slot keeps
   its best-scoring box and the rest go.

Neither rule can change which slots are occupied: a slot with five boxes and a
slot with one both mean occupied. They change how much noise everything
downstream has to carry, which is why this runs before the vote filter, the
live overlay and the plate reader rather than being applied at each of them.
"""

from __future__ import annotations

from .assignment import assign_detection
from .constants import SAME_VEHICLE_IOU
from .detection import Detection
from .slot_map import SlotMap


def group_detections_by_slot(
    detections: list[Detection], slot_map: SlotMap
) -> dict[str, list[Detection]]:
    """Every detection that landed inside a slot, keyed by slot id.

    Detections belonging to no slot are dropped - see rule 1 above. Slots
    holding nothing are absent rather than mapped to an empty list; callers
    needing a full roster iterate `slot_map.slots`.
    """
    grouped: dict[str, list[Detection]] = {}
    for detection in detections:
        slot = assign_detection(detection, slot_map.slots)
        if slot is not None:
            grouped.setdefault(slot.id, []).append(detection)
    return grouped


def resolve_slot_detections(
    detections: list[Detection], slot_map: SlotMap
) -> dict[str, Detection]:
    """The ONE vehicle in each slot, keyed by slot id.

    This is what the live view draws and what state is decided from. Feeding
    the raw list to either meant a single car appearing three times over, and
    boxes floating over furniture in a view an operator is meant to trust.
    """
    return {
        slot_id: _best_of(group)
        for slot_id, group in group_detections_by_slot(detections, slot_map).items()
    }


def occupied_slot_ids(detections: list[Detection], slot_map: SlotMap) -> set[str]:
    """Slots holding a vehicle in THIS frame.

    Raw, unfiltered output. Used directly it flickers - feed it through
    SlotMapFilter before anyone sees it.
    """
    return set(group_detections_by_slot(detections, slot_map))


def count_detections_per_slot(
    detections: list[Detection], slot_map: SlotMap
) -> dict[str, int]:
    """How many DISTINCT vehicles landed in each slot.

    Two or more in one slot means the polygon was drawn across the row behind
    it. That is a mistake worth catching while the installer is still on the
    ladder, so it drives an alert rather than being silently averaged away.

    "Distinct" is the load-bearing word. Counting boxes instead reported three
    vehicles in a bay holding one car - the model returns that car as both car
    and truck, and the detector's per-class NMS cannot merge across classes.
    The warning then fired continuously and stopped meaning anything, which is
    the failure mode a diagnostic can least afford.
    """
    grouped = group_detections_by_slot(detections, slot_map)
    return {slot.id: _distinct_vehicles(grouped.get(slot.id, [])) for slot in slot_map.slots}


def _best_of(group: list[Detection]) -> Detection:
    """The box that best represents a slot: highest score, largest on a tie.

    The area tie-break is not decoration. A camera run near the confidence
    floor - which is where a stock model has to sit to see these vehicles at
    all - produces ties often, and without a second key the winner could
    alternate between two boxes on consecutive frames, jittering the overlay
    while nothing in the bay moved.
    """
    return max(group, key=lambda item: (item.confidence, item.width * item.height))


def _distinct_vehicles(group: list[Detection]) -> int:
    """Count separate vehicles in one slot, merging repeat boxes of one car.

    Greedy, best score first: a box counts only if it does not substantially
    overlap one already counted. The same shape as NMS and for the same
    reason, but run per slot and ACROSS classes - precisely the case the
    detector's own per-class NMS cannot see.
    """
    kept: list[Detection] = []
    for detection in sorted(group, key=lambda item: -item.confidence):
        if all(_iou(detection, other) < SAME_VEHICLE_IOU for other in kept):
            kept.append(detection)
    return len(kept)


def _iou(a: Detection, b: Detection) -> float:
    """Intersection over union of two boxes. 0.0 when they do not overlap."""
    overlap_w = min(a.x2, b.x2) - max(a.x1, b.x1)
    overlap_h = min(a.y2, b.y2) - max(a.y1, b.y1)
    if overlap_w <= 0.0 or overlap_h <= 0.0:
        return 0.0
    intersection = overlap_w * overlap_h
    union = a.width * a.height + b.width * b.height - intersection
    # A zero-area box cannot overlap anything; guard the division rather than
    # trusting upstream never to emit one.
    return intersection / union if union > 0.0 else 0.0
