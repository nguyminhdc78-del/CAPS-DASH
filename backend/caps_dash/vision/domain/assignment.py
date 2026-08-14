"""Deciding which slot a detected vehicle is parked in.

No AI here. The detector only says "there is a vehicle at these coordinates";
turning that into "slot A2 is occupied" is plain geometry, and keeping it
separate is what lets the team change models, or install in a new building,
without retraining anything.

Strictly ONE box against the slot map. Reducing a whole frame's detections to
a verdict per bay - dropping what falls outside every slot, and collapsing
repeat boxes of one car - is `slot_detections`.
"""

from __future__ import annotations

from .constants import MIN_BAND_COVERAGE
from .detection import Detection
from .geometry import Point, bottom_band_points, ground_point, point_in_polygon
from .slot_map import Bounds, Slot


def assign_detection(detection: Detection, slots: list[Slot]) -> Slot | None:
    """Find the slot this vehicle occupies, or None.

    Two steps, in order:

    1. Does the ground point fall inside a slot? Most accurate, and immune to
       the tall-vehicle-assigned-to-the-row-behind failure.
    2. If no polygon contains it, measure how much of the bounding box's bottom
       band overlaps each slot and take the best - provided it clears
       MIN_BAND_COVERAGE. This rescues slots drawn a few pixels short, which
       previously reported free while a car sat plainly inside them.
    """
    point = ground_point(detection.x1, detection.y1, detection.x2, detection.y2)
    hits = [
        slot
        for slot in slots
        # Bounding-box reject first; ray casting only for the survivors.
        if _within(point, slot.bounds) and point_in_polygon(point, slot.polygon)
    ]
    if hits:
        # Overlapping polygons: the smaller one is the more specific slot.
        return min(hits, key=lambda slot: slot.area)

    # Computed once per detection, not once per slot.
    samples = bottom_band_points(detection.x1, detection.y1, detection.x2, detection.y2)
    sample_count = len(samples)
    band = (detection.x1, min(y for _, y in samples), detection.x2, detection.y2)

    best: Slot | None = None
    best_coverage = 0.0
    for slot in slots:
        # A slot whose box does not even touch the band cannot cover 40% of it.
        if not _overlaps(band, slot.bounds):
            continue
        inside = sum(1 for sample in samples if point_in_polygon(sample, slot.polygon))
        coverage = inside / sample_count
        if coverage > best_coverage:
            best, best_coverage = slot, coverage

    return best if best_coverage >= MIN_BAND_COVERAGE else None


def _within(point: Point, bounds: Bounds) -> bool:
    x, y = point
    min_x, min_y, max_x, max_y = bounds
    return min_x <= x <= max_x and min_y <= y <= max_y


def _overlaps(a: Bounds, b: Bounds) -> bool:
    """Axis-aligned rectangle intersection test."""
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])
