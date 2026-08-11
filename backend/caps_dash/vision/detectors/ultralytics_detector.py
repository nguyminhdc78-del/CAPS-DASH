"""Ultralytics-backed detector. Dev-only - never on the deployed board.

`ultralytics` is AGPL-3.0 and this project's source is published as a
competition condition, so it must never become a hard runtime dependency.
The import happens lazily INSIDE `__init__`, not at module level, so simply
importing this module - which the factory does whenever it is asked to build
any backend - never touches the package. Only actually constructing this
class does.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from ...errors.codes import ErrorCode
from ...errors.exceptions import AppError
from ..domain import Detection
from .base import VehicleDetector
from .constants import VEHICLE_CLASS_LABELS


class UltralyticsVehicleDetector(VehicleDetector):
    """Runs a `.pt` checkpoint directly through Ultralytics, for local dev only."""

    def __init__(self, weights_path: Path, confidence: float = 0.25) -> None:
        super().__init__(confidence)
        try:
            from ultralytics import YOLO  # type: ignore[attr-defined]
        except ImportError as exc:
            raise AppError(
                "ultralytics is not installed. Install the 'vision-dev' extra for "
                "local development ONLY: pip install -e \".[vision-dev]\" - "
                "it must never be installed on the deployed board.",
                code=ErrorCode.MODEL_UNAVAILABLE,
            ) from exc

        self._weights_path = weights_path
        self._model: Any = YOLO(str(weights_path))

    @property
    def name(self) -> str:
        return f"ultralytics:{self._weights_path.stem}"

    def detect(self, frame: np.ndarray) -> list[Detection]:
        results = self._model.predict(
            frame,
            conf=self.confidence,
            classes=list(VEHICLE_CLASS_LABELS),
            verbose=False,
        )
        detections: list[Detection] = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                class_id = int(box.cls[0])
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
                detections.append(
                    Detection(
                        x1=x1,
                        y1=y1,
                        x2=x2,
                        y2=y2,
                        confidence=float(box.conf[0]),
                        label=VEHICLE_CLASS_LABELS.get(class_id, "car"),
                    )
                )
        return detections

    def close(self) -> None:
        self._model = None
