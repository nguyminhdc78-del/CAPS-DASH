"""Loops a video file as a frame source, re-encoding each frame to JPEG.

Re-encoding happens IN the source so the contract stays "bytes in, bytes
out" for every implementation of `FrameSource` - callers never need to know
whether a given camera is a real ESP32-CAM or a recorded clip.
"""

from __future__ import annotations

from pathlib import Path

import cv2

from ...db.types import utc_now
from ...observability.logging_setup import get_logger
from .base import Frame, FrameSource, failed_frame
from .jpeg_utils import encode_jpeg

logger = get_logger(__name__)

DEFAULT_JPEG_QUALITY = 85


class VideoFileSource(FrameSource):
    """Reads frames from `path`, looping back to the start on EOF."""

    def __init__(
        self, camera_id: int, path: Path, jpeg_quality: int = DEFAULT_JPEG_QUALITY
    ) -> None:
        self._camera_id = camera_id
        self._path = path
        self._jpeg_quality = jpeg_quality
        self._capture: cv2.VideoCapture | None = None
        self._fail_streak = 0

    @property
    def camera_id(self) -> int:
        return self._camera_id

    @property
    def fail_streak(self) -> int:
        return self._fail_streak

    def read(self) -> Frame:
        capture = self._ensure_capture()
        if capture is None:
            self._fail_streak += 1
            return failed_frame(self._camera_id, f"cannot open video: {self._path}")

        ok, image = capture.read()
        if not ok:
            # EOF: loop rather than starve the pipeline on a short demo clip.
            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, image = capture.read()
        if not ok or image is None:
            self._fail_streak += 1
            return failed_frame(self._camera_id, "video read failed even after rewind to start")

        jpeg_bytes = encode_jpeg(image, self._jpeg_quality)
        self._fail_streak = 0
        return Frame(
            camera_id=self._camera_id,
            timestamp=utc_now(),
            image=image,
            jpeg_bytes=jpeg_bytes,
            ok=True,
        )

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def _ensure_capture(self) -> cv2.VideoCapture | None:
        if self._capture is not None:
            return self._capture
        capture = cv2.VideoCapture(str(self._path))
        if not capture.isOpened():
            capture.release()
            return None
        self._capture = capture
        return self._capture
