"""Vehicle detector contract.

Swapping ONNX for Ultralytics, or a future MaixCAM/TFLite backend, must never
require a change anywhere else in the pipeline - this ABC is the seam that
buys that. Every implementation returns `Detection` objects from the domain
package; nothing downstream needs to know which model produced them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from ..domain import Detection
from .constants import MAX_CONFIDENCE, MIN_CONFIDENCE


class VehicleDetector(ABC):
    """Finds vehicles in one frame.

    Backends: `onnx` (production), `ultralytics` (dev-only export helper /
    local testing), `fake` (deterministic, drives tests and CI without a
    model file or hardware).
    """

    def __init__(self, confidence: float = 0.25) -> None:
        self._confidence = _clamp(confidence)

    @property
    def confidence(self) -> float:
        return self._confidence

    @confidence.setter
    def confidence(self, value: float) -> None:
        """Adjustable while running, clamped rather than rejected.

        The right threshold depends on lighting, and discovering it is wrong
        during a demo is too late to fix by editing a file and restarting.
        Clamping (instead of raising on an out-of-range value) means a
        fat-fingered number from an admin control degrades gracefully
        instead of 500-ing the request.
        """
        self._confidence = _clamp(value)

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identity for logs, e.g. `onnx:yolo-vehicle` or `fake`."""

    @abstractmethod
    def detect(self, frame: np.ndarray) -> list[Detection]:
        """Find vehicles in `frame` (a decoded BGR image, HWC uint8).

        Boxes come back in the SAME pixel space as `frame` - see
        `Detection`'s coordinate contract. Letterboxing and rescaling to a
        model's own input size are entirely this method's problem to undo.
        """

    def warmup(self, frame: np.ndarray) -> None:
        """Run one throwaway inference before anything is timed.

        The first call through most inference backends builds graphs and
        allocators and runs roughly an order of magnitude slower than steady
        state. Excluding it from every latency measurement is the difference
        between a real benchmark and a fictional one.
        """
        self.detect(frame)

    def close(self) -> None:  # noqa: B027 - optional hook, deliberately not abstract
        """Release backend resources.

        Not abstract on purpose: most detectors hold nothing that needs
        releasing, and forcing every one of them to write an empty override
        adds noise without adding safety.
        """


def _clamp(value: float) -> float:
    return max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, float(value)))
