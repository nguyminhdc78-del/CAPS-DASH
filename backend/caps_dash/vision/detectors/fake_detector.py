"""Deterministic detector for tests and CI.

Required infrastructure, not test scaffolding: there is no camera hardware
and no committed model checkpoint on a fresh clone until `models/*.onnx` is
exported, so this is what lets the whole pipeline - source to slot state - be
driven and asserted on without either.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ..domain import Detection
from .base import VehicleDetector


class FakeVehicleDetector(VehicleDetector):
    """Returns boxes from a script instead of running a model.

    `script` is a list of per-call results; `detect()` cycles through it
    regardless of the frame it is given, so a test can assert exact slot
    transitions frame by frame. An empty/omitted script always returns no
    detections, which is a valid and useful default (an "empty garage" fake).
    """

    def __init__(
        self,
        script: Sequence[list[Detection]] | None = None,
        *,
        confidence: float = 0.25,
    ) -> None:
        super().__init__(confidence)
        self._script: list[list[Detection]] = list(script) if script else []
        self._call_count = 0

    @property
    def name(self) -> str:
        return "fake"

    @property
    def call_count(self) -> int:
        """Number of `detect()` calls so far - handy for test assertions."""
        return self._call_count

    def detect(self, frame: np.ndarray) -> list[Detection]:
        del frame  # scripted output is independent of the actual pixels
        if not self._script:
            return []
        boxes = self._script[self._call_count % len(self._script)]
        self._call_count += 1
        return boxes
