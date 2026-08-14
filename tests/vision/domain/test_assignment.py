"""Two-step slot assignment."""

from __future__ import annotations

from caps_dash.vision.domain import (
    Detection,
    Slot,
    SlotMap,
    assign_detection,
    count_detections_per_slot,
    group_detections_by_slot,
    occupied_slot_ids,
    resolve_slot_detections,
)


def _rect(slot_id: str, x1: float, y1: float, x2: float, y2: float) -> Slot:
    return Slot(slot_id, [(x1, y1), (x2, y1), (x2, y2), (x1, y2)])


def _car(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    confidence: float = 0.8,
    label: str = "car",
) -> Detection:
    return Detection(x1=x1, y1=y1, x2=x2, y2=y2, confidence=confidence, label=label)


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


def test_count_ignores_a_detection_that_lands_in_no_slot() -> None:
    """An unassigned vehicle must not raise and must not be counted anywhere."""
    slot_map = SlotMap(slots=[_rect("A1", 0, 0, 100, 100)], width=200, height=200)
    counts = count_detections_per_slot([_car(500, 500, 560, 580)], slot_map)
    assert counts == {"A1": 0}


def test_count_reports_zero_for_empty_slots() -> None:
    slot_map = SlotMap(
        slots=[_rect("A1", 0, 0, 100, 100), _rect("A2", 100, 0, 200, 100)],
        width=200,
        height=100,
    )
    counts = count_detections_per_slot([_car(40, 10, 60, 90)], slot_map)
    assert counts == {"A1": 1, "A2": 0}


def test_one_car_returned_as_two_classes_counts_once() -> None:
    """A stock COCO model calls the same car both car and truck.

    Per-class NMS inside the detector cannot merge those, so without the
    overlap test this reported two vehicles in a bay holding one and the
    install-time warning fired continuously.
    """
    slot_map = SlotMap(slots=[_rect("A1", 0, 0, 100, 100)], width=100, height=100)
    car = _car(30, 10, 70, 90, confidence=0.08)
    same_car_as_truck = _car(31, 12, 69, 91, confidence=0.01, label="truck")

    assert count_detections_per_slot([car, same_car_as_truck], slot_map) == {"A1": 1}


# --- ROI gating and one-vehicle-per-slot ------------------------------------


def test_detections_outside_every_slot_are_dropped() -> None:
    """The ROI is the filter: a mouse on the desk is not evidence about a bay."""
    slot_map = SlotMap(slots=[_rect("A1", 0, 0, 100, 100)], width=400, height=400)
    parked = _car(40, 10, 60, 90)
    not_a_car = _car(300, 300, 360, 380)

    assert group_detections_by_slot([parked, not_a_car], slot_map) == {"A1": [parked]}
    assert resolve_slot_detections([parked, not_a_car], slot_map) == {"A1": parked}


def test_a_slot_resolves_to_exactly_one_vehicle() -> None:
    """Three boxes on one car collapse to the best-scoring box."""
    slot_map = SlotMap(slots=[_rect("A1", 0, 0, 100, 100)], width=100, height=100)
    weak = _car(30, 10, 70, 90, confidence=0.01)
    best = _car(31, 11, 71, 91, confidence=0.08)
    middling = _car(29, 9, 69, 89, confidence=0.04, label="truck")

    resolved = resolve_slot_detections([weak, best, middling], slot_map)

    assert resolved == {"A1": best}


def test_equal_confidence_resolves_to_the_larger_box() -> None:
    """Deterministic tie-break, so the overlay does not jitter between frames."""
    slot_map = SlotMap(slots=[_rect("A1", 0, 0, 100, 100)], width=100, height=100)
    small = _car(40, 40, 60, 90, confidence=0.05)
    large = _car(20, 10, 80, 95, confidence=0.05)

    assert resolve_slot_detections([small, large], slot_map) == {"A1": large}
    assert resolve_slot_detections([large, small], slot_map) == {"A1": large}


def test_resolution_keeps_one_vehicle_in_each_of_several_slots() -> None:
    slot_map = SlotMap(
        slots=[_rect("A1", 0, 0, 100, 100), _rect("A2", 100, 0, 200, 100)],
        width=200,
        height=100,
    )
    a1 = _car(40, 10, 60, 90, confidence=0.3)
    a1_duplicate = _car(41, 11, 61, 91, confidence=0.1)
    a2 = _car(140, 10, 160, 90, confidence=0.2)

    resolved = resolve_slot_detections([a1, a1_duplicate, a2], slot_map)

    assert resolved == {"A1": a1, "A2": a2}


def test_resolution_never_changes_which_slots_are_occupied() -> None:
    """Collapsing to one box per slot must not lose an occupied slot."""
    slot_map = SlotMap(
        slots=[_rect("A1", 0, 0, 100, 100), _rect("A2", 100, 0, 200, 100)],
        width=200,
        height=100,
    )
    detections = [
        _car(40, 10, 60, 90),
        _car(41, 11, 61, 91),
        _car(140, 10, 160, 90),
        _car(500, 500, 560, 580),
    ]

    assert set(resolve_slot_detections(detections, slot_map)) == occupied_slot_ids(
        detections, slot_map
    )


def test_empty_detections_resolve_to_nothing() -> None:
    slot_map = SlotMap(slots=[_rect("A1", 0, 0, 100, 100)], width=100, height=100)
    assert resolve_slot_detections([], slot_map) == {}
    assert group_detections_by_slot([], slot_map) == {}
