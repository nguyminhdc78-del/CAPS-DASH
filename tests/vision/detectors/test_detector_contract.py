"""The detector ABC's shared behaviour, and the factory."""

from __future__ import annotations

import numpy as np
import pytest

from caps_dash.config.settings import Settings
from caps_dash.vision.detectors.constants import MAX_CONFIDENCE, MIN_CONFIDENCE
from caps_dash.vision.detectors.detector_factory import build_detector
from caps_dash.vision.detectors.fake_detector import FakeVehicleDetector
from caps_dash.vision.domain import (
    Detection,
    Slot,
    SlotMap,
    SlotState,
    build_filter,
    occupied_slot_ids,
)

FRAME = np.zeros((480, 640, 3), dtype=np.uint8)


def car(x1: float, y1: float, x2: float, y2: float) -> Detection:
    return Detection(x1=x1, y1=y1, x2=x2, y2=y2, confidence=0.9, label="car")


def test_confidence_is_clamped_not_rejected() -> None:
    """An admin typing a silly number should degrade, not 500 the request."""
    detector = FakeVehicleDetector()

    detector.confidence = 5.0
    assert detector.confidence == MAX_CONFIDENCE

    detector.confidence = -1.0
    assert detector.confidence == MIN_CONFIDENCE

    detector.confidence = 0.4
    assert detector.confidence == pytest.approx(0.4)


def test_confidence_clamps_at_construction_too() -> None:
    assert FakeVehicleDetector(confidence=99.0).confidence == MAX_CONFIDENCE


def test_fake_detector_replays_its_script_in_order() -> None:
    script = [[car(0, 0, 10, 10)], [], [car(5, 5, 20, 20), car(30, 30, 40, 40)]]
    detector = FakeVehicleDetector(script)

    assert len(detector.detect(FRAME)) == 1
    assert detector.detect(FRAME) == []
    assert len(detector.detect(FRAME)) == 2
    # Cycles, so a worker loop can run indefinitely against a fixed script.
    assert len(detector.detect(FRAME)) == 1
    assert detector.call_count == 4


def test_fake_detector_defaults_to_an_empty_garage() -> None:
    assert FakeVehicleDetector().detect(FRAME) == []


def test_warmup_runs_one_inference() -> None:
    """Excluded from timings on purpose: the first call is an order slower."""
    detector = FakeVehicleDetector([[car(0, 0, 1, 1)]])
    detector.warmup(FRAME)
    assert detector.call_count == 1


def test_factory_builds_the_backend_named_in_settings() -> None:
    settings = Settings(detector_backend="fake", secret_key="test")
    assert build_detector(settings).name == "fake"


def test_fake_detector_drives_the_whole_pipeline_without_hardware() -> None:
    """Source-free end to end: scripted boxes -> slot states.

    This is why the fake backend exists. No camera, no model file, and the
    full assignment plus vote path is still exercised.
    """
    slot_map = SlotMap(
        slots=[
            Slot("A1", [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]),
            Slot("A2", [(100.0, 0.0), (200.0, 0.0), (200.0, 100.0), (100.0, 100.0)]),
        ],
        width=640,
        height=480,
        camera_id="demo",
    )
    # A car parked in A1 for every frame; A2 stays empty.
    detector = FakeVehicleDetector([[car(30.0, 20.0, 70.0, 90.0)]])
    vote_filter = build_filter(slot_map.slot_ids, window=3, threshold=2)

    states: dict[str, SlotState] = {}
    for _ in range(3):
        detections = detector.detect(FRAME)
        states = vote_filter.update(occupied_slot_ids(detections, slot_map))

    assert states["A1"] is SlotState.OCCUPIED
    assert states["A2"] is SlotState.FREE
