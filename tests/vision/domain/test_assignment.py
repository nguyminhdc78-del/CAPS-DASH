"""Two-step slot assignment."""

from __future__ import annotations

from caps_dash.vision.domain import (
    Detection,
    Slot,
    SlotMap,
    assign_detection,
    count_detections_per_slot,
    occupied_slot_ids,
)


def _rect(slot_id: str, x1: float, y1: float, x2: float, y2: float) -> Slot:
    return Slot(slot_id, [(x1, y1), (x2, y1), (x2, y2), (x1, y2)])


def _car(x1: float, y1: float, x2: float, y2: float) -> Detection:
    return Detection(x1=x1, y1=y1, x2=x2, y2=y2, confidence=0.8, label="car")


def test_ground_point_inside_a_slot_wins_immediately() -> None:
    slot = _rect("A1", 0, 0, 100, 100)
    assert assign_detection(_car(40, 10, 60, 90), [slot]) is slot


def test_overlapping_slots_resolve_to_the_smallest() -> None:
    """A nested polygon is the more specific slot, whatever the list order."""
    big = _rect("BIG", 0, 0, 100, 100)
    small = _rect("SMALL", 40, 40, 70, 70)
    car = _car(45, 20, 65, 60)  # ground point (55, 60) is inside both

    assert assign_detection(car, [big, small]) is small
    assert assign_detection(car, [small, big]) is small


def test_band_fallback_rescues_a_slot_drawn_slightly_short() -> None:
    """Ground point falls just outside, but most of the box bottom is inside."""
    slot = _rect("A1", 0, 0, 100, 100)
    # Ground point at y=104: four pixels below the polygon's bottom edge.
    car = _car(30, 40, 70, 104)
    assert assign_detection(car, [slot]) is slot


def test_a_car_merely_clipping_the_edge_is_refused() -> None:
    """Coverage below 0.40 must not claim the slot."""
    slot = _rect("A1", 0, 0, 100, 100)
    # Almost entirely to the right of the slot, only a sliver overlapping.
    car = _car(95, 60, 200, 160)
    assert assign_detection(car, [slot]) is None


def test_a_car_nowhere_near_any_slot_is_unassigned() -> None:
    slot = _rect("A1", 0, 0, 100, 100)
    assert assign_detection(_car(500, 500, 560, 580), [slot]) is None


def test_no_slots_at_all_is_handled() -> None:
    assert assign_detection(_car(0, 0, 10, 10), []) is None


def test_occupied_slot_ids_collects_one_frame() -> None:
    slot_map = SlotMap(
        slots=[_rect("A1", 0, 0, 100, 100), _rect("A2", 100, 0, 200, 100)],
        width=200,
        height=100,
    )
    detections = [_car(40, 10, 60, 90), _car(140, 10, 160, 90)]
    assert occupied_slot_ids(detections, slot_map) == {"A1", "A2"}


def test_occupied_slot_ids_is_empty_without_detections() -> None:
    slot_map = SlotMap(slots=[_rect("A1", 0, 0, 100, 100)], width=100, height=100)
    assert occupied_slot_ids([], slot_map) == set()


def test_two_cars_in_one_slot_is_reported() -> None:
    """Signals a polygon drawn across the row behind - an install-time mistake."""
    slot_map = SlotMap(slots=[_rect("A1", 0, 0, 200, 100)], width=200, height=100)
    counts = count_detections_per_slot([_car(10, 10, 40, 90), _car(150, 10, 180, 90)], slot_map)
    assert counts == {"A1": 2}


def test_count_reports_zero_for_empty_slots() -> None:
    slot_map = SlotMap(
        slots=[_rect("A1", 0, 0, 100, 100), _rect("A2", 100, 0, 200, 100)],
        width=200,
        height=100,
    )
    counts = count_detections_per_slot([_car(40, 10, 60, 90)], slot_map)
    assert counts == {"A1": 1, "A2": 0}
