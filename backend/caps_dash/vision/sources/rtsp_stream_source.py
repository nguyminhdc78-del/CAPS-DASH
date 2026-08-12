"""Reads an RTSP camera through OpenCV's FFMPEG backend.

WHY THIS HAS NO READER THREAD, unlike `esp32cam_stream_source`. That source
runs one because an ESP32-CAM's MJPEG connection hands over whatever arrives
and `read()` would otherwise wait on the network. RTSP measured on the board
against the reference camera (640x480 HEVC at 30 fps) behaves the opposite
way:

  * the board decodes at ~35 fps over TCP - faster than the source sends, so
    there is nothing to catch up on;
  * after deliberately not reading for five seconds, only three frames came
    back without waiting. FFMPEG bounds its own queue, so lag stays at about
    a tenth of a second instead of growing without limit.

A thread draining 30 fps of HEVC would therefore burn most of a core decoding
frames it then throws away, on a board that is also running YOLO26. Reading
one frame per tick costs one decode and is at most ~3 frames stale.

TCP, not UDP. UDP decoded faster (~50 fps) but loses packets, and a partly
decoded frame is not a missing frame - it is a plausible-looking wrong one,
which is exactly what a detector must never be fed.
"""

from __future__ import annotations

import os

import cv2

from ...db.types import utc_now
from ...observability.credential_redaction import redact_credentials
from ...observability.logging_setup import get_logger
from .base import Frame, FrameSource, failed_frame
from .jpeg_utils import encode_jpeg

logger = get_logger(__name__)

DEFAULT_JPEG_QUALITY = 85

# Consecutive failures before the capture is torn down and reopened. A camera
# that is unplugged and plugged back in leaves `read()` returning False
# forever otherwise - the handle stays open, it just never yields again.
REOPEN_AFTER_FAILURES = 5


def _capture_options(timeout_s: float) -> str:
    """FFMPEG options string, `key;value` pairs joined by `|`.

    The timeout is what stops a vanished camera blocking `read()` - and with
    it the worker thread the loop is waiting on - indefinitely. FFMPEG wants
    microseconds. Both spellings are passed because the option was renamed
    from `stimeout` to `timeout`, and which one a build accepts depends on
    its FFMPEG version; the unrecognised one is ignored.
    """
    micros = max(int(timeout_s * 1_000_000), 1_000_000)
    return f"rtsp_transport;tcp|stimeout;{micros}|timeout;{micros}"


class RtspStreamSource(FrameSource):
    """One RTSP capture per camera, opened lazily and reopened when it dies."""

    def __init__(
        self,
        camera_id: int,
        url: str,
        timeout_s: float,
        *,
        jpeg_quality: int = DEFAULT_JPEG_QUALITY,
    ) -> None:
        self._camera_id = camera_id
        self._url = url
        self._timeout_s = timeout_s
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
        """Newest available frame. Never raises - see `base.py`."""
        try:
            capture = self._ensure_capture()
        except Exception as exc:  # cv2 raises bare cv2.error, not a subclass we can name
            return self._fail(f"cannot open RTSP stream: {type(exc).__name__}: {exc}")

        if capture is None:
            return self._fail("cannot open RTSP stream")

        try:
            ok, image = capture.read()
        except Exception as exc:
            return self._fail(f"RTSP read failed: {type(exc).__name__}: {exc}")

        if not ok or image is None:
            return self._fail("RTSP stream returned no frame")

        # Encoded here rather than in a reader thread: this is the one frame
        # per tick that is actually consumed, so this is the only frame worth
        # spending the ~60 ms the board needs to encode one on.
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
        self._release()

    # --- internals -----------------------------------------------------------

    def _ensure_capture(self) -> cv2.VideoCapture | None:
        if self._capture is not None:
            return self._capture

        # Process-global and read by FFMPEG when the capture is constructed,
        # so it is set here rather than at import: nothing else in this
        # process opens an RTSP capture, and a module-level assignment would
        # apply to every `VideoCapture` the process ever makes.
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = _capture_options(self._timeout_s)

        capture = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
        if not capture.isOpened():
            capture.release()
            return None

        logger.info("rtsp_stream_opened", camera_id=self._camera_id)
        self._capture = capture
        return self._capture

    def _release(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def _fail(self, error: str) -> Frame:
        self._fail_streak += 1
        if self._fail_streak >= REOPEN_AFTER_FAILURES:
            # Force the next read to build a fresh capture. Counting is not
            # reset here: the worker's own offline threshold is what decides
            # when the camera counts as down, and clearing the streak on a
            # reconnect attempt would hide a camera that is failing forever.
            self._release()
        safe = redact_credentials(error)
        return failed_frame(self._camera_id, safe)
