"""Geometry primitives."""

from __future__ import annotations

import time

from caps_dash.vision.domain import (
    Detection,
    Slot,
    SlotMap,
    assign_detection,
    bottom_band_points,
    ground_point,
    point_in_polygon,
    polygon_area,
    scale_polygon,
)

SQUARE: list[tuple[float, float]] = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
# Concave: a square with a notch bitten out of the right edge.
CHEVRON: list[tuple[float, float]] = [
    (0.0, 0.0),
    (10.0, 0.0),
    (10.0, 10.0),
    (5.0, 5.0),
    (0.0, 10.0),
]


def test_ground_point_is_the_bottom_edge_midpoint() -> None:
    assert ground_point(10.0, 20.0, 30.0, 60.0) == (20.0, 60.0)


def test_ground_point_ignores_the_top_edge() -> None:
    """Changing y1 must not move the ground point - only the bottom matters."""
    assert ground_point(10.0, 0.0, 30.0, 60.0) == ground_point(10.0, 55.0, 30.0, 60.0)


def test_point_in_polygon_inside_and_outside() -> None:
    assert point_in_polygon((5.0, 5.0), SQUARE)
    assert not point_in_polygon((15.0, 5.0), SQUARE)
    assert not point_in_polygon((5.0, -1.0), SQUARE)


def test_point_in_polygon_handles_concave_shapes() -> None:
    """The notch must read as outside, which a convex-only test would miss.

    Sample points are kept clear of the edges on purpose: a point lying exactly
    on a boundary is undefined for ray casting, as `point_in_polygon` documents.
    At x=2 the notch edge runs through y=8, so 6 is used instead.
    """
    assert point_in_polygon((2.0, 6.0), CHEVRON)
    assert not point_in_polygon((5.0, 9.0), CHEVRON)


def test_polygon_area_matches_shoelace() -> None:
    assert polygon_area(SQUARE) == 100.0


def test_polygon_area_ignores_winding_direction() -> None:
    assert polygon_area(list(reversed(SQUARE))) == 100.0


def test_degenerate_polygon_has_zero_area() -> None:
    """Collinear points. Guarded at the API layer so it cannot win a tie-break."""
    assert polygon_area([(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)]) == 0.0


def test_bottom_band_points_stay_in_the_lower_band() -> None:
    points = bottom_band_points(0.0, 0.0, 100.0, 100.0)
    assert len(points) == 25
    # band = 0.30 of a 100-tall box, so every sample sits below y = 70.
    assert all(y > 70.0 for _, y in points)
    assert all(0.0 <= x <= 100.0 for x, _ in points)


def test_scale_polygon_applies_each_factor_to_its_own_axis() -> None:
    assert scale_polygon([(10.0, 20.0)], 2.0, 0.5) == [(20.0, 10.0)]


def test_tall_vehicle_is_assigned_to_the_front_slot() -> None:
    """The headline reason for using the ground point.

    Two slot rows, one behind the other. A tall van parked in the FRONT row has
    a bounding box whose centre falls into the BACK row's polygon. The ground
    point keeps it in the front row; the centre would not.
    """
    back = Slot("BACK", [(0.0, 0.0), (100.0, 0.0), (100.0, 60.0), (0.0, 60.0)])
    front = Slot("FRONT", [(0.0, 60.0), (100.0, 60.0), (100.0, 100.0), (0.0, 100.0)])
    slot_map = SlotMap(slots=[back, front], width=100, height=100)

    # Centre lands at y=50, comfortably inside BACK; wheels at y=90 in FRONT.
    van = Detection(x1=40.0, y1=10.0, x2=60.0, y2=90.0, confidence=0.9, label="truck")

    assigned = assign_detection(van, slot_map.slots)
    assert assigned is not None
    assert assigned.id == "FRONT"

    # And confirm the trap is real: the bbox centre lands in the back row.
    centre = ((van.x1 + van.x2) / 2, (van.y1 + van.y2) / 2)
    assert point_in_polygon(centre, back.polygon)


def test_assignment_does_not_degrade_pathologically() -> None:
    """Guards against an accidentally quadratic assignment, nothing more.

    Deliberately a loose bound. A wall-clock assertion on a shared development
    machine measures the machine, not the code - a tight threshold here just
    flakes whenever something else is compiling. The real budget is generous:
    six cameras at one frame every three seconds is two assignments a second,
    so even 50 ms per call would be invisible.

    Actual performance is a question for the target board, and must be
    MEASURED there rather than asserted here.
    """
    slots = [
        Slot(
            f"S{i}",
            [(i * 10.0, 0.0), (i * 10.0 + 9, 0.0), (i * 10.0 + 9, 40.0), (i * 10.0, 40.0)],
        )
        for i in range(12)
    ]
    detections = [
        Detection(x1=i * 5.0, y1=5.0, x2=i * 5.0 + 8, y2=35.0, confidence=0.7) for i in range(20)
    ]

    start = time.perf_counter()
    for detection in detections:
        assign_detection(detection, slots)
    elapsed_ms = (time.perf_counter() - start) * 1000

    # 20x the observed cost on an idle dev machine: catches a regression that
    # changes the complexity class, ignores ordinary scheduling noise.
    assert elapsed_ms < 150.0, f"assignment took {elapsed_ms:.2f} ms"
