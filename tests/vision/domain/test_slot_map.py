"""`Slot`/`SlotMap` surface not already exercised by the assignment and
aspect-ratio-rescale suites: state read/write, id listing, and the compact
wire payload that is the whole privacy argument of this design made concrete.
"""

from __future__ import annotations

from caps_dash.vision.domain import Detection, Slot, SlotMap, SlotState


def _rect(slot_id: str, x1: float, y1: float, x2: float, y2: float) -> Slot:
    return Slot(slot_id, [(x1, y1), (x2, y1), (x2, y2), (x1, y2)])


# --- Detection -----------------------------------------------------------


def test_detection_width_and_height_are_derived_from_the_box() -> None:
    detection = Detection(x1=10.0, y1=20.0, x2=50.0, y2=90.0, confidence=0.9)
    assert detection.width == 40.0
    assert detection.height == 70.0


# --- SlotMap.states / apply_states -----------------------------------------


def test_states_reads_every_slots_current_state() -> None:
    slot_map = SlotMap(
        slots=[
            Slot("A1", [(0, 0)], state=SlotState.OCCUPIED),
            Slot("A2", [(0, 0)], state=SlotState.FREE),
        ],
        width=100,
        height=100,
    )
    assert slot_map.states() == {"A1": SlotState.OCCUPIED, "A2": SlotState.FREE}


def test_apply_states_writes_back_and_leaves_unknown_ids_alone() -> None:
    slot_map = SlotMap(
        slots=[_rect("A1", 0, 0, 10, 10), _rect("A2", 10, 0, 20, 10)], width=20, height=10
    )

    # "GONE" does not name a slot on this map - must not raise, must not
    # create anything.
    slot_map.apply_states({"A1": SlotState.OCCUPIED, "GONE": SlotState.FREE})

    assert slot_map.states() == {"A1": SlotState.OCCUPIED, "A2": SlotState.UNKNOWN}


# --- SlotMap.slot_ids / to_payload ------------------------------------------


def test_slot_ids_lists_every_slot_in_order() -> None:
    slot_map = SlotMap(
        slots=[_rect("A1", 0, 0, 10, 10), _rect("A2", 10, 0, 20, 10)], width=20, height=10
    )
    assert slot_map.slot_ids == ["A1", "A2"]


def test_to_payload_is_a_compact_symbol_string_never_the_image() -> None:
    slot_map = SlotMap(
        slots=[
            Slot("A1", [(0, 0)], state=SlotState.OCCUPIED),
            Slot("A2", [(0, 0)], state=SlotState.FREE),
            Slot("A3", [(0, 0)], state=SlotState.UNKNOWN),
        ],
        width=100,
        height=100,
        camera_id="CAM-01",
    )
    assert slot_map.to_payload() == "CAM-01|A1:1 A2:0 A3:?"
