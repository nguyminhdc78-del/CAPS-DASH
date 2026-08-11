"""Letterbox geometry and non-max suppression."""

from __future__ import annotations

import numpy as np

from caps_dash.vision.detectors.box_utils import letterbox, nms, unletterbox_boxes


def test_letterbox_produces_a_square_and_preserves_aspect_ratio() -> None:
    image = np.zeros((480, 640, 3), dtype=np.uint8)
    padded, scale, (pad_x, pad_y) = letterbox(image, 640)

    assert padded.shape[:2] == (640, 640)
    assert scale == 1.0
    # 640x480 into a 640 square: nothing added horizontally, 160 split vertically.
    assert (pad_x, pad_y) == (0.0, 80.0)


def test_letterbox_round_trip_on_a_non_square_frame() -> None:
    """The coordinate contract: boxes come back in ORIGINAL frame pixels.

    Non-square on purpose. A square test frame would pass even if padding were
    ignored entirely, which is exactly the bug worth catching - the same class
    of silent coordinate error as the shared-scale-factor one in the domain.
    """
    orig_w, orig_h = 1600, 900
    image = np.zeros((orig_h, orig_w, 3), dtype=np.uint8)
    padded, scale, pad = letterbox(image, 640)

    # A box covering the lower-right quadrant of the ORIGINAL frame.
    original = np.array([[800.0, 450.0, 1600.0, 900.0]])

    # Forward: original -> letterboxed square, the way a model would see it.
    forward = original.copy()
    forward[:, [0, 2]] = forward[:, [0, 2]] * scale + pad[0]
    forward[:, [1, 3]] = forward[:, [1, 3]] * scale + pad[1]

    # Every mapped corner must land inside the padded square.
    assert forward.min() >= 0
    assert forward.max() <= padded.shape[0]

    recovered = unletterbox_boxes(forward, scale, pad, orig_w, orig_h)
    assert np.allclose(recovered, original, atol=1.0)


def test_unletterbox_clips_to_the_frame() -> None:
    """A model can predict slightly outside the image; boxes must not escape it."""
    boxes = np.array([[-50.0, -50.0, 900.0, 900.0]])
    out = unletterbox_boxes(boxes, scale=1.0, pad=(0.0, 0.0), orig_w=640, orig_h=480)
    assert out[0, 0] == 0.0
    assert out[0, 1] == 0.0
    assert out[0, 2] == 640.0
    assert out[0, 3] == 480.0


def test_nms_drops_a_duplicate_of_the_same_vehicle() -> None:
    boxes = np.array(
        [
            [100.0, 100.0, 200.0, 200.0],
            [105.0, 105.0, 205.0, 205.0],  # ~85% IoU: the same car found twice
        ]
    )
    scores = np.array([0.9, 0.8])
    assert nms(boxes, scores, 0.45) == [0]


def test_nms_keeps_two_cars_parked_side_by_side() -> None:
    boxes = np.array([[0.0, 0.0, 100.0, 100.0], [120.0, 0.0, 220.0, 100.0]])
    scores = np.array([0.9, 0.85])
    assert sorted(nms(boxes, scores, 0.45)) == [0, 1]


def test_nms_returns_highest_score_first() -> None:
    boxes = np.array([[0.0, 0.0, 10.0, 10.0], [500.0, 500.0, 510.0, 510.0]])
    scores = np.array([0.3, 0.95])
    assert nms(boxes, scores, 0.45)[0] == 1


def test_nms_handles_no_boxes() -> None:
    assert nms(np.zeros((0, 4)), np.zeros(0), 0.45) == []


def test_nms_tolerates_zero_area_boxes() -> None:
    """A degenerate box must not divide by zero and poison the whole frame."""
    boxes = np.array([[10.0, 10.0, 10.0, 10.0], [0.0, 0.0, 5.0, 5.0]])
    scores = np.array([0.9, 0.8])
    assert sorted(nms(boxes, scores, 0.45)) == [0, 1]
