"""Vehicle detector backends behind one ABC.

`ultralytics_detector` is intentionally NOT re-exported here - importing it
is fine (the lazy import lives inside its class), but keeping it out of this
package's star surface means nothing accidentally instantiates it outside an
explicit, deliberate import.
"""

from __future__ import annotations

from .base import VehicleDetector
from .constants import MAX_CONFIDENCE, MIN_CONFIDENCE
from .detector_factory import build_detector
from .fake_detector import FakeVehicleDetector
from .onnx_detector import OnnxVehicleDetector

__all__ = [
    "MAX_CONFIDENCE",
    "MIN_CONFIDENCE",
    "FakeVehicleDetector",
    "OnnxVehicleDetector",
    "VehicleDetector",
    "build_detector",
]
