"""Builds a `VehicleDetector` from settings.

The only place `detector_backend` is turned into a class - implementations
never read settings directly (the reference project scattered hardcoded
paths and thresholds across modules; this factory is what replaces that).
"""

from __future__ import annotations

from ...config.settings import Settings
from .base import VehicleDetector
from .fake_detector import FakeVehicleDetector
from .onnx_detector import OnnxVehicleDetector


def build_detector(settings: Settings) -> VehicleDetector:
    """Construct the detector named by `settings.detector_backend`.

    `settings.detector_backend` is a `Literal["onnx", "ultralytics", "fake"]`,
    so this match is exhaustive by construction - adding a new backend value
    to the settings type without adding a case here fails at typecheck time,
    not at 2am on the board.
    """
    match settings.detector_backend:
        case "onnx":
            return OnnxVehicleDetector(
                model_path=settings.model_path,
                input_size=settings.inference_input_size,
                confidence=settings.detector_confidence,
                threads=settings.inference_threads,
            )
        case "fake":
            return FakeVehicleDetector(confidence=settings.detector_confidence)
        case "ultralytics":
            # Imported lazily here too, one level up from the class itself:
            # even touching this module must not require the AGPL-3.0
            # package unless this exact backend is actually selected.
            from .ultralytics_detector import UltralyticsVehicleDetector

            return UltralyticsVehicleDetector(
                weights_path=settings.model_path, confidence=settings.detector_confidence
            )
