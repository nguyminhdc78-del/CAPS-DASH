"""Regression test for the silent shared-scale-factor bug.

This is the reason the domain phase exists as its own unit.

A slot map is drawn over a 16:9 still. The live camera delivers 10:7. If the
polygon is rescaled with ONE shared factor instead of independent x and y
factors, every slot drifts off the cars and reports FREE forever - and nothing
raises, nothing logs, and the dashboard looks perfectly healthy.

Both directions are asserted: the correct implementation finds the car, and the
buggy variant provably does not. Without that second assertion the test would
still pass if `fit_to_frame` were "simplified" back into the bug.
"""

from __future__ import annotations

from caps_dash.vision.domain import Detection, Slot, SlotMap, assign_detection, scale_polygon

# Slot map authored against a 1600x900 (16:9) still.
SOURCE_W, SOURCE_H = 1600, 900
# The camera actually delivers 640x448 (10:7) - a different aspect ratio.
FRAME_W, FRAME_H = 640, 448


def _slot_map_16x9() -> SlotMap:
    """One slot covering the lower-right quadrant of the source still."""
    return SlotMap(
        slots=[Slot("A1", [(800.0, 450.0), (1600.0, 450.0), (1600.0, 900.0), (800.0, 900.0)])],
        width=SOURCE_W,
        height=SOURCE_H,
        camera_id="01",
    )


def _fit_with_single_shared_factor(slot_map: SlotMap, frame_w: int, frame_h: int) -> SlotMap:
    """The bug, reproduced deliberately: one factor applied to both axes."""
    shared = min(frame_w / slot_map.width, frame_h / slot_map.height)
    return SlotMap(
        slots=[
            Slot(s.id, scale_polygon(s.polygon, shared, shared), s.state) for s in slot_map.slots
        ],
        width=frame_w,
        height=frame_h,
        camera_id=slot_map.camera_id,
    )


# A car parked in that slot, as it appears in the live 640x448 frame.
# Ground point is (495, 420): inside the correctly rescaled polygon, well below
# the bottom edge of the wrongly rescaled one.
PARKED_CAR = Detection(x1=430.0, y1=300.0, x2=560.0, y2=420.0, confidence=0.8, label="car")


def test_independent_axis_factors_find_the_car() -> None:
    fitted = _slot_map_16x9().fit_to_frame(FRAME_W, FRAME_H)
    assert assign_detection(PARKED_CAR, fitted.slots) is not None


def test_single_shared_factor_silently_loses_the_car() -> None:
    """Proves the negative case: this is what the bug looks like."""
    broken = _fit_with_single_shared_factor(_slot_map_16x9(), FRAME_W, FRAME_H)
    assert assign_detection(PARKED_CAR, broken.slots) is None


def test_rescale_stretches_each_axis_by_its_own_ratio() -> None:
    fitted = _slot_map_16x9().fit_to_frame(FRAME_W, FRAME_H)
    xs = [x for x, _ in fitted.slots[0].polygon]
    ys = [y for _, y in fitted.slots[0].polygon]

    # x: 1600 -> 640 is exactly 0.4
    assert min(xs) == 320.0
    assert max(xs) == 640.0
    # y: 900 -> 448 is ~0.4978, NOT 0.4. If these were equal the bug is back.
    assert round(min(ys), 2) == 224.0
    assert round(max(ys), 2) == 448.0


def test_identical_size_returns_the_same_object() -> None:
    """Cheap path: no allocation when the frame already matches the source."""
    slot_map = _slot_map_16x9()
    assert slot_map.fit_to_frame(SOURCE_W, SOURCE_H) is slot_map
