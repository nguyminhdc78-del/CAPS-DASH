"""Cropping a bay, and judging what came back from the reader.

The model itself is not exercised here - it downloads weights on first use and
a test suite that needs the network is a test suite that fails on a train. The
logic around it is what this file covers, and it is the part that decides
whether a guard sees a plate at all.
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import pytest

from caps_dash.vision import plate_reader
from caps_dash.vision.plate_reader import (
    MIN_PLATE_WIDTH_PX,
    crop_to_polygon,
    looks_like_plate,
    read_plate,
)

FRAME_W, FRAME_H = 640, 480
BAY = [(200.0, 200.0), (400.0, 200.0), (400.0, 360.0), (200.0, 360.0)]


def frame() -> np.ndarray:
    return np.full((FRAME_H, FRAME_W, 3), 90, dtype=np.uint8)


# --- cropping ----------------------------------------------------------------


def test_the_crop_is_wider_than_the_bay() -> None:
    """A plate sits at a car's nose or tail, which is frequently just outside
    the painted box - especially when the car is parked badly. Cropping to the
    polygon exactly would slice the plate off in precisely the cases where
    knowing the plate matters."""
    crop = crop_to_polygon(frame(), BAY)

    assert crop is not None
    height, width = crop.shape[:2]
    assert width > 200
    assert height > 160


def test_a_bay_at_the_frame_edge_is_clamped_not_dropped() -> None:
    """A slot drawn against the edge of the view is ordinary, not an error."""
    edge = [(0.0, 0.0), (120.0, 0.0), (120.0, 90.0), (0.0, 90.0)]
    crop = crop_to_polygon(frame(), edge)

    assert crop is not None
    assert crop.shape[0] > 0 and crop.shape[1] > 0


def test_a_polygon_off_the_frame_returns_nothing() -> None:
    """Happens when a slot map is stale against a camera that changed
    resolution. A bad reason to raise three layers down inside a camera loop."""
    assert crop_to_polygon(frame(), [(9000.0, 9000.0), (9100.0, 9000.0), (9100.0, 9100.0)]) is None


def test_a_degenerate_polygon_returns_nothing() -> None:
    assert crop_to_polygon(frame(), [(10.0, 10.0), (20.0, 20.0)]) is None


# --- judging a reading -------------------------------------------------------


class _Box:
    def __init__(self, x1: float, x2: float) -> None:
        self.x1, self.x2 = x1, x2
        self.y1, self.y2 = 0.0, 20.0


class _Detection:
    def __init__(self, width: float, confidence: float) -> None:
        self.bounding_box = _Box(0.0, width)
        self.confidence = confidence


class _Ocr:
    def __init__(self, text: str) -> None:
        self.text = text


class _Result:
    def __init__(self, text: str | None, width: float, confidence: float) -> None:
        self.detection = _Detection(width, confidence)
        # `ALPRResult.ocr` really is None when the plate was found but not read.
        self.ocr = _Ocr(text) if text is not None else None


class _FakeReader:
    def __init__(self, results: list[_Result]) -> None:
        self._results = results

    def predict(self, _image: np.ndarray) -> list[_Result]:
        return self._results


@pytest.fixture(autouse=True)
def _no_real_model() -> Iterator[None]:
    """Never load the real reader: it fetches weights over the network."""
    plate_reader.reset_reader()
    yield
    plate_reader.reset_reader()


def with_results(monkeypatch: pytest.MonkeyPatch, results: list[_Result]) -> None:
    monkeypatch.setattr(plate_reader, "_get_reader", lambda: _FakeReader(results))


def test_a_clear_plate_is_read_and_normalised(monkeypatch: pytest.MonkeyPatch) -> None:
    """Separators are a rendering convention that varies between plates, so
    they are stripped at the boundary rather than at every query."""
    with_results(monkeypatch, [_Result("30H-832.31", 140, 0.9)])

    read = read_plate(frame(), BAY, 0.3)

    assert read is not None
    assert read.plate == "30H83231"


def test_a_plate_too_small_to_trust_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Measured on this toolchain: one-row plates read perfectly from 60 px and
    failed at 40. Below the floor the characters are not there to read, and a
    confident-looking guess is worse than silence."""
    with_results(monkeypatch, [_Result("30H83231", MIN_PLATE_WIDTH_PX - 1, 0.95)])

    assert read_plate(frame(), BAY, 0.3) is None


def test_a_low_confidence_detection_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    with_results(monkeypatch, [_Result("30H83231", 140, 0.10)])

    assert read_plate(frame(), BAY, 0.3) is None


def test_the_widest_plate_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two plates inside one bay's crop means the neighbouring car has crept
    into the margin. The nearer car is the bigger one, and it is the one
    actually parked here."""
    with_results(
        monkeypatch,
        [_Result("11A11111", 80, 0.9), _Result("30H83231", 160, 0.9), _Result("22B22222", 70, 0.9)],
    )

    read = read_plate(frame(), BAY, 0.3)

    assert read is not None
    assert read.plate == "30H83231"


def test_a_plate_found_but_not_read_does_not_hide_one_that_was(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The detector locating a plate the OCR could not read is ordinary at a
    bad angle, and it arrives as `ocr=None`. Reaching through it would raise
    and abandon every other result in the same crop - including the wider,
    readable plate belonging to the car actually parked here."""
    with_results(monkeypatch, [_Result(None, 200, 0.9), _Result("30H83231", 140, 0.9)])

    read = read_plate(frame(), BAY, 0.3)

    assert read is not None
    assert read.plate == "30H83231"


def test_nothing_found_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ordinary outcome for a car parked nose-in or a bay at a bad angle.
    A car park where half the plates are unreadable still counts its slots."""
    with_results(monkeypatch, [])

    assert read_plate(frame(), BAY, 0.3) is None


def test_a_reader_that_explodes_does_not_take_the_camera_with_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Occupancy is the product; plates are an addition to it. A corrupt weight
    file must not stop a camera counting cars."""

    class _Broken:
        def predict(self, _image: np.ndarray) -> list[_Result]:
            raise RuntimeError("onnx session died")

    monkeypatch.setattr(plate_reader, "_get_reader", lambda: _Broken())

    assert read_plate(frame(), BAY, 0.3) is None


# --- the plausibility check --------------------------------------------------


@pytest.mark.parametrize("text", ["30H83231", "51A12345", "29H1234", "99A53457"])
def test_real_plates_pass(text: str) -> None:
    assert looks_like_plate(text) is True


@pytest.mark.parametrize("text", ["", "AB", "TOYOTA", "HONDACIVICTYPER"])
def test_bumper_stickers_do_not(text: str) -> None:
    """`TOYOTA` has no digits; the long one is beyond any plate's length. The
    check is deliberately loose - rejecting a real plate because it failed
    somebody's remembered regex is worse than storing an odd-looking one a
    guard can see is wrong."""
    assert looks_like_plate(text) is False
