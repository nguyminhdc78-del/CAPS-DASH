"""Reading the licence plate of the car that just parked in a slot.

Everything here blocks and belongs in the inference thread pool, never on the
event loop.

WHY THIS IS AFFORDABLE AT ALL, in one measurement. Detecting and reading a
plate over a whole 640x480 frame costs **2642 ms** on the board, against the
1477 ms the vehicle detector already spends every tick. Run per tick that is
unaffordable. It is not run per tick: a plate is only wanted at the moment a
slot becomes occupied, which the vote filter already announces, so the
steady-state cost is zero.

The trigger pays for itself twice. When a slot transitions its polygon is
known, so the frame is cropped to that bay first and the plate then fills a
far larger share of the input - which is what lets the cheaper 384-pixel
detector do the work.

Plates carry only Latin letters and digits, in Vietnam as elsewhere -
`51A-123.45`. There is no Vietnamese-language model involved and none is
needed; "does this OCR support Vietnamese?" is a question about reading prose.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..observability.logging_setup import get_logger

logger = get_logger(__name__)

# Measured on the board 2026-08-13, on a frame containing four real plates:
#   yolo-v9-t-384   1067 ms, found 1 of 4
#   yolo-v9-t-640   2642 ms, found 3 of 4, all read correctly
# The 384 model is the default because it runs against a CROP of one slot, not
# the whole frame, so the plate occupies far more of its input than it did in
# that measurement. Switch to 640 if reads are being missed.
DETECTOR_MODEL = "yolo-v9-t-384-license-plate-end2end"
OCR_MODEL = "cct-s-v1-global-model"

# Grow the slot polygon's bounding box by this fraction before cropping. A
# polygon is drawn around the parking bay, and a car's plate sits at its nose
# or tail - frequently just outside the painted box, especially when the car
# is badly parked.
CROP_MARGIN = 0.25

# Below this, a plate is too small to read. Measured on this toolchain:
# synthetic one-row plates read perfectly from 60 px and failed at 40. Vendor
# guides claim 100-150 px; they are describing other pipelines.
MIN_PLATE_WIDTH_PX = 60

# One reader per worker thread, for the same reason the vehicle detector has
# one: model objects are not documented as thread-safe, and a shared one fails
# silently rather than loudly. With a single-worker pool this holds exactly one
# in memory.
_local = threading.local()


@dataclass(frozen=True, slots=True)
class PlateRead:
    """One plate, read from one slot, with what it cost to get it."""

    plate: str
    confidence: float
    width_px: int
    process_ms: float


def _get_reader() -> Any:
    reader = getattr(_local, "reader", None)
    if reader is None:
        # Imported here, not at module scope: the plate models are an optional
        # capability, and a deployment without them must still start and count
        # cars rather than fail at import.
        from fast_alpr import ALPR

        reader = ALPR(detector_model=DETECTOR_MODEL, ocr_model=OCR_MODEL)
        _local.reader = reader
        logger.info("plate_reader_loaded", detector=DETECTOR_MODEL, ocr=OCR_MODEL)
    return reader


def reset_reader() -> None:
    """Drop this thread's reader. For tests, and for a model change."""
    _local.reader = None


def crop_to_polygon(image: np.ndarray, polygon: list[tuple[float, float]]) -> np.ndarray | None:
    """The bay, plus a margin, as its own image.

    Returns None when the polygon lands outside the frame entirely - which
    happens if a slot map is stale against a camera that changed resolution,
    and is a bad reason to raise three layers down.
    """
    if len(polygon) < 3:
        return None

    height, width = image.shape[:2]
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    pad_x = (max(xs) - min(xs)) * CROP_MARGIN
    pad_y = (max(ys) - min(ys)) * CROP_MARGIN

    x1 = max(0, int(min(xs) - pad_x))
    y1 = max(0, int(min(ys) - pad_y))
    x2 = min(width, int(max(xs) + pad_x))
    y2 = min(height, int(max(ys) + pad_y))

    if x2 - x1 < 2 or y2 - y1 < 2:
        return None
    return image[y1:y2, x1:x2]


def read_plate(
    image: np.ndarray, polygon: list[tuple[float, float]], min_confidence: float
) -> PlateRead | None:
    """Find and read the plate of whatever is parked in this slot.

    `None` means no plate worth trusting, which is the normal outcome for a
    car parked nose-in, a bay seen from a bad angle, or a camera that simply
    cannot resolve the characters. It is not an error and must not be logged
    as one - a car park where half the plates are unreadable still counts
    slots correctly.
    """
    crop = crop_to_polygon(image, polygon)
    if crop is None or crop.size == 0:
        return None

    started = time.perf_counter()
    try:
        results = _get_reader().predict(crop)
    except Exception:
        # A missing model download, a corrupt weight file, an ONNX error - none
        # of it may take the camera loop down. Occupancy is the product;
        # plates are an addition to it.
        logger.warning("plate_read_failed", exc_info=True)
        return None
    process_ms = (time.perf_counter() - started) * 1000.0

    best: PlateRead | None = None
    for result in results:
        # `ALPRResult.ocr` is None when the detector found a plate the OCR could
        # not read - ordinary at a bad angle, and common enough that reaching
        # through it would abandon a good plate found earlier in the same crop.
        if result.ocr is None:
            continue
        text = "".join(ch for ch in str(result.ocr.text or "").upper() if ch.isalnum())
        if not text:
            continue
        box = result.detection.bounding_box
        width_px = int(box.x2 - box.x1)
        confidence = float(result.detection.confidence)
        if width_px < MIN_PLATE_WIDTH_PX or confidence < min_confidence:
            continue
        # Widest wins. Two plates inside one bay's crop means the neighbouring
        # car has crept into the margin, and the nearer plate is the bigger one.
        if best is None or width_px > best.width_px:
            best = PlateRead(text, confidence, width_px, process_ms)

    return best


def looks_like_plate(text: str) -> bool:
    """A weak sanity check, deliberately not a format validator.

    Vietnamese plates run 7 to 9 characters and mix digits and letters. Anything
    far outside that is the OCR reading a bumper sticker, not a plate. It is
    kept loose on purpose: rejecting a real plate because it does not match a
    regex someone wrote from memory is worse than storing an odd-looking one,
    which a guard can see is wrong.
    """
    return 6 <= len(text) <= 10 and any(ch.isdigit() for ch in text)
