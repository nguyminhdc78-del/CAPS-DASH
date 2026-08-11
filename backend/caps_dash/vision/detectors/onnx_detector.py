"""ONNX vehicle detector - the production backend.

CPU is the baseline execution provider on the aarch64 target (Arduino UNO Q /
QRB2210). Any accelerator provider is unverified on that SoC and must stay
opt-in behind an explicit `providers` argument, never assumed by default.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort

from ...errors.codes import ErrorCode
from ...errors.exceptions import AppError
from ...observability.logging_setup import get_logger
from ..domain import Detection
from .base import VehicleDetector
from .box_utils import letterbox
from .onnx_decode import decode_yolo_output

logger = get_logger(__name__)

# The QNN execution provider (Qualcomm's NPU/DSP path) is unverified on the
# QRB2210 - its Hexagon DSP targets sensor fusion and audio, not vision. CPU
# stays the only default until someone actually measures QNN on the board.
DEFAULT_PROVIDERS = ["CPUExecutionProvider"]


class OnnxVehicleDetector(VehicleDetector):
    """Runs a YOLO `.onnx` export via onnxruntime."""

    def __init__(
        self,
        model_path: Path,
        input_size: int = 640,
        confidence: float = 0.25,
        providers: list[str] | None = None,
    ) -> None:
        super().__init__(confidence)
        if not model_path.is_file():
            # A clear, actionable message here - not an onnxruntime stack
            # trace three layers down - is the whole point of this check.
            raise AppError(
                f"Vehicle detection model not found at {model_path}. "
                "Export or copy yolo-vehicle.onnx into models/ - see models/README.md.",
                code=ErrorCode.MODEL_UNAVAILABLE,
            )
        self._model_path = model_path
        self._input_size = input_size
        self._session: ort.InferenceSession | None = ort.InferenceSession(
            str(model_path), providers=providers or DEFAULT_PROVIDERS
        )
        self._input_name = self._session.get_inputs()[0].name

        output_shape = self._session.get_outputs()[0].shape
        if len(output_shape) != 3:
            # Fail at load time, not three frames into a demo: an export with
            # a different head shape needs a decoder change, not a mystery
            # runtime crash.
            raise AppError(
                f"Unexpected ONNX output rank {len(output_shape)} from {model_path.name} "
                f"(expected 3 dims: batch + channels + anchors); got shape {output_shape}",
                code=ErrorCode.MODEL_UNAVAILABLE,
            )
        logger.info(
            "onnx_session_loaded",
            model=model_path.name,
            output_shape=str(output_shape),
            providers=self._session.get_providers(),
        )

    @property
    def name(self) -> str:
        return f"onnx:{self._model_path.stem}"

    def detect(self, frame: np.ndarray) -> list[Detection]:
        if self._session is None:
            raise AppError("Detector already closed", code=ErrorCode.MODEL_UNAVAILABLE)

        orig_h, orig_w = frame.shape[:2]
        padded, scale, pad = letterbox(frame, self._input_size)
        tensor = _to_input_tensor(padded)

        raw_output = self._session.run(None, {self._input_name: tensor})[0]
        return decode_yolo_output(raw_output, scale, pad, orig_w, orig_h, self.confidence)

    def close(self) -> None:
        # onnxruntime has no explicit close(); dropping the reference frees
        # the session and its arena on next GC. Explicit here so every
        # backend offers the same close() regardless of its internals.
        self._session = None


def _to_input_tensor(padded_bgr: np.ndarray) -> np.ndarray:
    """BGR uint8 HWC -> RGB float32 NCHW in [0, 1], contiguous for onnxruntime."""
    rgb = padded_bgr[:, :, ::-1]
    normalized = rgb.astype(np.float32) / 255.0
    chw = normalized.transpose(2, 0, 1)
    return np.ascontiguousarray(chw[np.newaxis, ...])
