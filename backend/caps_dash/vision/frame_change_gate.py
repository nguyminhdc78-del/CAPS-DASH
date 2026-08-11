"""Decides whether a frame is worth running the detector on.

Parked cars do not move. Between one entry and the next, every frame a ceiling
camera produces is the same picture, and running YOLO on each of them spends
~616 ms of a four-core board's budget to re-derive an answer that has not
changed. Comparing two downscaled greyscale frames costs 2.7 ms - 0.4% of an
inference - so the cheap check pays for itself the first time it says "skip".

TWO RULES, and the second is what makes the first safe.

**Compare against the last INFERRED frame, not the previous frame.** A car
easing into a slot over ten frames changes each frame only slightly; measured
frame-to-frame it never crosses the threshold and the detector never runs.
Measured against the last frame the detector actually saw, the difference
accumulates until it does.

**Infer anyway every `force_interval_s`.** Slow drift - dusk, a light
switched on, the sensor's own auto-exposure - can move the whole picture
below the threshold one small step at a time. The heartbeat bounds how long
the system can be wrong, and keeps feeding the vote filter fresh evidence.

Thresholds are a property of the installation, not of this code: the noise
floor measured on the reference camera was ~0.5 mean absolute difference with
a worst case of 1.2, on a very dark scene. The default sits above that with
margin. A brighter camera is noisier and may need more.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np

# The frame is compared at this size, not full resolution. Small enough that
# sensor noise averages out and the comparison is nearly free; large enough
# that one car entering one slot still moves the number.
SAMPLE_WIDTH = 64
SAMPLE_HEIGHT = 48


@dataclass(frozen=True, slots=True)
class GateDecision:
    """Whether to run the detector, and the reason - which goes into the logs."""

    infer: bool
    reason: str
    difference: float


class FrameChangeGate:
    """Per-camera state for the change check. Not thread-safe: one camera loop owns one."""

    def __init__(self, *, threshold: float, force_interval_s: float) -> None:
        self._threshold = threshold
        self._force_interval_s = force_interval_s
        self._reference: np.ndarray | None = None
        self._last_infer_at = 0.0

    def evaluate(self, image: np.ndarray) -> GateDecision:
        """Judge one frame. Call `mark_inferred` if the caller acts on `infer=True`."""
        sample = _downscale(image)

        if self._reference is None:
            return GateDecision(True, "first_frame", 0.0)

        difference = float(np.abs(sample - self._reference).mean())

        if difference >= self._threshold:
            return GateDecision(True, "changed", difference)

        elapsed = time.monotonic() - self._last_infer_at
        if elapsed >= self._force_interval_s:
            return GateDecision(True, "heartbeat", difference)

        return GateDecision(False, "unchanged", difference)

    def mark_inferred(self, image: np.ndarray) -> None:
        """Record that the detector ran on this frame; it becomes the reference."""
        self._reference = _downscale(image)
        self._last_infer_at = time.monotonic()

    def reset(self) -> None:
        """Forget the reference, so the next frame is inferred unconditionally.

        Used when the slot map changes: the previous reference describes a
        layout that no longer applies, and the first frame under a new map
        must be looked at properly.
        """
        self._reference = None
        self._last_infer_at = 0.0


def _downscale(image: np.ndarray) -> np.ndarray:
    """Greyscale, small, signed.

    `int16` rather than `uint8` because the difference of two uint8 arrays
    wraps around: |20 - 30| would come out as 246, and a darkening frame would
    read as an enormous change.
    """
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    small = cv2.resize(
        grey, (SAMPLE_WIDTH, SAMPLE_HEIGHT), interpolation=cv2.INTER_AREA
    )
    return small.astype(np.int16)
