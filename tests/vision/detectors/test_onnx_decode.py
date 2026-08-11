"""Decoding a raw YOLO head into Detections.

Driven with synthetic tensors rather than a real model: the .onnx is exported
separately and a fresh clone may not have one, so these tests must not depend
on it.
"""

from __future__ import annotations

import numpy as np
import pytest

from caps_dash.vision.detectors.constants import VEHICLE_CLASS_LABELS
from caps_dash.vision.detectors.onnx_decode import decode_yolo_output

NUM_CLASSES = 80
CAR, MOTORCYCLE, BUS, TRUCK, PERSON, DOG = 2, 3, 5, 7, 0, 16


# Real exports emit thousands of anchors. The decoder tells the two possible
# head layouts apart by comparing axis lengths, so a toy tensor with fewer
# anchors than channels would be read transposed - pad to a realistic count
# rather than test a shape that cannot occur.
ANCHORS = 300


def make_head(rows: list[tuple[tuple[float, float, float, float], int, float]]) -> np.ndarray:
    """Build a `[1, 4 + num_classes, ANCHORS]` tensor - the stock transposed export."""
    assert len(rows) <= ANCHORS
    output = np.zeros((4 + NUM_CLASSES, ANCHORS), dtype=np.float32)
    for index, ((cx, cy, w, h), class_id, score) in enumerate(rows):
        output[0:4, index] = (cx, cy, w, h)
        output[4 + class_id, index] = score
    # The remaining anchors keep all-zero class scores and are dropped by the
    # confidence filter, exactly as empty anchors are in a real frame.
    return output[np.newaxis, ...]


def decode(head: np.ndarray, confidence: float = 0.25) -> list:
    # Identity transform: scale 1, no padding, so boxes come out in input pixels.
    return decode_yolo_output(head, scale=1.0, pad=(0.0, 0.0), orig_w=640, orig_h=640,
                              confidence=confidence)


def test_decodes_a_single_car() -> None:
    detections = decode(make_head([((100, 100, 40, 20), CAR, 0.9)]))
    assert len(detections) == 1
    found = detections[0]
    assert found.label == "car"
    # float32 tensor, so compare approximately.
    assert found.confidence == pytest.approx(0.9)
    # cxcywh -> xyxy
    assert (found.x1, found.y1, found.x2, found.y2) == (80.0, 90.0, 120.0, 110.0)


def test_drops_boxes_below_the_confidence_threshold() -> None:
    head = make_head([((100, 100, 40, 20), CAR, 0.9), ((300, 300, 40, 20), CAR, 0.10)])
    assert len(decode(head, confidence=0.25)) == 1


def test_confidence_threshold_is_applied_at_decode_time() -> None:
    head = make_head([((100, 100, 40, 20), CAR, 0.30)])
    assert len(decode(head, confidence=0.25)) == 1
    assert decode(head, confidence=0.50) == []


def test_keeps_only_vehicle_classes() -> None:
    """A person walking past a slot must never mark it occupied."""
    head = make_head(
        [
            ((100, 100, 40, 20), CAR, 0.9),
            ((200, 100, 20, 40), PERSON, 0.95),
            ((300, 100, 30, 30), DOG, 0.95),
        ]
    )
    detections = decode(head)
    assert [d.label for d in detections] == ["car"]


def test_recognises_every_configured_vehicle_class() -> None:
    head = make_head(
        [
            ((100, 100, 40, 20), CAR, 0.9),
            ((200, 200, 40, 20), MOTORCYCLE, 0.9),
            ((300, 300, 60, 30), BUS, 0.9),
            ((400, 400, 60, 30), TRUCK, 0.9),
        ]
    )
    assert sorted(d.label for d in decode(head)) == sorted(VEHICLE_CLASS_LABELS.values())


def test_suppresses_a_duplicate_detection_of_one_vehicle() -> None:
    head = make_head(
        [((100, 100, 40, 20), CAR, 0.9), ((102, 101, 40, 20), CAR, 0.7)]
    )
    assert len(decode(head)) == 1


def test_nms_is_per_class_so_an_overlapping_bus_and_car_both_survive() -> None:
    head = make_head(
        [((100, 100, 40, 20), CAR, 0.9), ((100, 100, 40, 20), BUS, 0.85)]
    )
    assert sorted(d.label for d in decode(head)) == ["bus", "car"]


def test_accepts_the_untransposed_head_layout() -> None:
    """Some exports emit `[1, N, 4 + classes]` already row-major."""
    row_major = np.transpose(make_head([((100, 100, 40, 20), CAR, 0.9)]), (0, 2, 1))
    assert row_major.shape == (1, ANCHORS, 4 + NUM_CLASSES)

    detections = decode(row_major)
    assert len(detections) == 1
    assert detections[0].label == "car"


def test_empty_output_yields_no_detections() -> None:
    """A head with zero anchors must return nothing, not raise.

    Regression: the row-count guard alone let this through to argmax, which
    raises on an empty sequence. Exports with NMS baked into the graph really
    do return zero rows on a quiet frame.
    """
    assert decode(np.zeros((1, 4 + NUM_CLASSES, 0), dtype=np.float32)) == []


def test_output_with_no_class_columns_yields_no_detections() -> None:
    assert decode(np.zeros((1, 4, ANCHORS), dtype=np.float32)) == []


def test_all_below_threshold_yields_no_detections() -> None:
    head = make_head([((100, 100, 40, 20), CAR, 0.01)])
    assert decode(head, confidence=0.5) == []


def test_boxes_are_mapped_back_through_the_letterbox() -> None:
    """The contract: coordinates returned are ORIGINAL-frame pixels."""
    head = make_head([((320.0, 320.0, 40.0, 40.0), CAR, 0.9)])
    detections = decode_yolo_output(
        head, scale=0.5, pad=(0.0, 80.0), orig_w=1280, orig_h=480, confidence=0.25
    )
    found = detections[0]
    # x: (320 +/- 20 - 0) / 0.5 ; y: (320 +/- 20 - 80) / 0.5
    assert (found.x1, found.x2) == (600.0, 680.0)
    assert (found.y1, found.y2) == (440.0, 480.0)
