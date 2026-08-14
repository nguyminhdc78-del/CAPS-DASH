"""Parking vision domain - standard library only.

Nothing in this package may import a third party. No numpy, no cv2, no ORM, no
web framework. A test walks every module's AST and fails the build if one
appears.

That constraint buys two things: the whole algorithm is testable without a
camera or a model, and it runs unchanged on hardware too constrained to carry
the usual scientific-Python stack.
"""

from __future__ import annotations

from .assignment import assign_detection
from .constants import (
    BAND_COLS,
    BAND_FRACTION,
    BAND_ROWS,
    DEFAULT_VOTE_THRESHOLD,
    DEFAULT_VOTE_WINDOW,
    MIN_BAND_COVERAGE,
    SAME_VEHICLE_IOU,
)
from .detection import Detection
from .geometry import (
    Point,
    Polygon,
    bottom_band_points,
    ground_point,
    point_in_polygon,
    polygon_area,
    scale_polygon,
)
from .slot_detections import (
    count_detections_per_slot,
    group_detections_by_slot,
    occupied_slot_ids,
    resolve_slot_detections,
)
from .slot_map import Slot, SlotMap
from .states import SlotState
from .vote_filter import SlotMapFilter, SlotVoteFilter, build_filter

__all__ = [
    "BAND_COLS",
    "BAND_FRACTION",
    "BAND_ROWS",
    "DEFAULT_VOTE_THRESHOLD",
    "DEFAULT_VOTE_WINDOW",
    "MIN_BAND_COVERAGE",
    "SAME_VEHICLE_IOU",
    "Detection",
    "Point",
    "Polygon",
    "Slot",
    "SlotMap",
    "SlotMapFilter",
    "SlotState",
    "SlotVoteFilter",
    "assign_detection",
    "bottom_band_points",
    "build_filter",
    "count_detections_per_slot",
    "ground_point",
    "group_detections_by_slot",
    "occupied_slot_ids",
    "point_in_polygon",
    "polygon_area",
    "resolve_slot_detections",
    "scale_polygon",
]
