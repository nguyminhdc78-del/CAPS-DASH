"""The CPU-bound half of a tick, run inside the inference thread pool.

Everything here blocks. It must never be called on the event loop - that is
what `loop.run_in_executor` is for, and why this is a separate module rather
than a method on the loop object.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import numpy as np

from ..config.settings import Settings
from ..errors.exceptions import UpstreamError
from ..vision.detectors.base import VehicleDetector
from ..vision.detectors.detector_factory import build_detector
from ..vision.domain import Detection

# One detector per worker thread. Model objects are not documented as
# thread-safe, and sharing one across threads risks silent corruption rather
# than a clean error. With the default pool size of 1 this holds exactly one
# model in memory, which is the point on a board with little RAM to spare.
_local = threading.local()


def get_thread_detector(settings: Settings) -> VehicleDetector:
    detector: VehicleDetector | None = getattr(_local, "detector", None)
    if detector is None:
        detector = build_detector(settings)
        _local.detector = detector
    return detector


def reset_thread_detector() -> None:
    """Drop this thread's detector. Used by tests and on backend changes."""
    _local.detector = None


@dataclass(frozen=True, slots=True)
class InferenceOutcome:
    detections: list[Detection]
    frame_w: int
    frame_h: int
    process_ms: float
    confidence: float


def run_inference(
    settings: Settings, image: np.ndarray, confidence: float
) -> InferenceOutcome:
    """Detect vehicles in an already-decoded frame.

    The frame arrives decoded because the source had to decode it anyway to
    prove the JPEG was not truncated. Decoding twice would double the cost of
    the most expensive non-inference step in the tick.
    """
    if image is None or image.size == 0:
        raise UpstreamError("Empty frame handed to the detector")

    detector = get_thread_detector(settings)
    # Applied per tick so an operator moving the slider takes effect on the
    # next frame, without restarting anything.
    detector.confidence = confidence

    height, width = image.shape[:2]
    started = time.perf_counter()
    detections = detector.detect(image)
    process_ms = (time.perf_counter() - started) * 1000.0

    return InferenceOutcome(
        detections=detections,
        frame_w=width,
        frame_h=height,
        process_ms=process_ms,
        confidence=detector.confidence,
    )
