"""Reads an RTSP camera through OpenCV's FFMPEG backend.

WHY A READER THREAD IS NOT OPTIONAL HERE, measured on the board against the
reference camera (640x480 HEVC at 30 fps).

An RTSP capture hands out frames in order, oldest first. It does not skip to
the newest one. So a worker ticking every 0.3 s consumes about 3 of the 30
frames the camera sends each second, and the other 27 queue up. Measured by
comparing each frame's own presentation timestamp against the wall clock:

    after  5.8 s of real time, the frame shown was from  0.4 s  -> 5.4 s late
    after 30.4 s of real time, the frame shown was from  1.8 s  -> 28.6 s late

The lag grows one second per second, without bound. Within a minute the
dashboard is showing a car park as it was a minute ago, which for this system
is worse than showing nothing.

So a thread drains the stream continuously and keeps only the newest frame,
and `read()` becomes a memory lookup. Cost, measured: `read()` is 17.0 ms a
frame here, so draining 30 fps spends about half of one core. `grab()` was
measured too, in case the drain could skip the BGR conversion for frames
nobody consumes - it came out at 19.2 ms, no cheaper at all, so the thread
just calls `read()`.

The frame is kept DECODED, unlike `esp32cam_stream_source` which keeps raw
JPEG. That source gets JPEG off the wire and decoding is the expensive part,
so it defers it; here decoding already happened inside `read()` and it is the
JPEG (6.5 ms) that is deferred to the frames actually consumed.

TCP, not UDP. UDP decoded faster in isolation but loses packets, and a partly
decoded frame is not a missing frame - it is a plausible-looking wrong one,
which is exactly what a detector must never be fed.
"""

from __future__ import annotations

import os
import threading
import time

import cv2
import numpy as np

from ...db.types import utc_now
from ...observability.credential_redaction import redact_credentials
from ...observability.logging_setup import get_logger
from .base import Frame, FrameSource, failed_frame
from .jpeg_utils import encode_jpeg

logger = get_logger(__name__)

DEFAULT_JPEG_QUALITY = 85

# A frame older than this is not "the current view" any more, so `read()`
# reports a failure rather than handing the worker a stale picture that would
# keep a dead camera looking alive.
DEFAULT_MAX_AGE_S = 5.0

INITIAL_BACKOFF_S = 1.0
MAX_BACKOFF_S = 30.0

# Consecutive failed reads before the capture is torn down and reopened. A
# camera that is unplugged and plugged back in leaves `read()` returning False
# forever otherwise - the handle stays open, it just never yields again.
REOPEN_AFTER_FAILURES = 5


def _capture_options(timeout_s: float) -> str:
    """FFMPEG options string, `key;value` pairs joined by `|`.

    The timeout is what stops a vanished camera blocking the reader thread
    forever. FFMPEG wants microseconds. Both spellings are passed because the
    option was renamed from `stimeout` to `timeout` and which one a build
    accepts depends on its FFMPEG version; the unrecognised one is ignored.
    """
    micros = max(int(timeout_s * 1_000_000), 1_000_000)
    return f"rtsp_transport;tcp|stimeout;{micros}|timeout;{micros}"


class RtspStreamSource(FrameSource):
    """One RTSP capture per camera, drained by a background thread."""

    def __init__(
        self,
        camera_id: int,
        url: str,
        timeout_s: float,
        *,
        jpeg_quality: int = DEFAULT_JPEG_QUALITY,
        max_age_s: float = DEFAULT_MAX_AGE_S,
    ) -> None:
        self._camera_id = camera_id
        self._url = url
        self._timeout_s = timeout_s
        self._jpeg_quality = jpeg_quality
        self._max_age_s = max_age_s

        # Only ever touched by the reader thread, plus `close()` after it has
        # been joined - never by both at once.
        self._capture: cv2.VideoCapture | None = None

        self._lock = threading.Lock()
        self._latest: np.ndarray | None = None
        self._latest_at = 0.0
        self._last_error = "stream has not connected yet"
        self._frames_seen = 0
        self._fail_streak = 0

        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name=f"rtsp-{camera_id}", daemon=True
        )
        self._thread.start()

    @property
    def camera_id(self) -> int:
        return self._camera_id

    @property
    def fail_streak(self) -> int:
        return self._fail_streak

    @property
    def frames_seen(self) -> int:
        """Frames the reader thread has decoded, for diagnostics."""
        return self._frames_seen

    def read(self) -> Frame:
        """Newest decoded frame. Never raises - see `base.py`."""
        with self._lock:
            image = self._latest
            age = time.monotonic() - self._latest_at
            error = self._last_error

        if image is None:
            return self._fail(error or "no frame yet")
        if age > self._max_age_s:
            return self._fail(f"stream stalled: newest frame is {age:.1f}s old")

        # Encoded here, not in the thread: this is the one frame per tick that
        # is actually consumed, and encoding all 30 a second would spend
        # another fifth of a core on frames nobody ever sees.
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
        self._stop.set()
        thread, self._thread = self._thread, None  # type: ignore[assignment]
        if thread is not None:
            # Joined, unlike the MJPEG source which leaves its thread to die.
            # That one only holds a socket; this one is inside `cv2` when it
            # blocks, and releasing a VideoCapture another thread is reading
            # is a crash rather than an error. The timeout is bounded by the
            # FFMPEG read timeout, so shutdown cannot hang on a dead camera.
            thread.join(timeout=self._timeout_s + 2.0)
            if thread.is_alive():
                # Leak the capture rather than release it underneath a live
                # reader. A leaked handle on a process that is shutting down
                # costs nothing; a segfault loses the shutdown.
                logger.warning("rtsp_reader_did_not_stop", camera_id=self._camera_id)
                return
        self._release()

    # --- reader thread -------------------------------------------------------

    def _run(self) -> None:
        backoff = INITIAL_BACKOFF_S
        while not self._stop.is_set():
            try:
                if self._drain():
                    backoff = INITIAL_BACKOFF_S
            except Exception as exc:
                self._record_error(f"{type(exc).__name__}: {exc}")
            self._release()
            if self._stop.is_set() or self._stop.wait(backoff):
                return
            backoff = min(backoff * 2, MAX_BACKOFF_S)

    def _drain(self) -> bool:
        """Hold the stream open, keeping the newest frame. Returns True if it
        ever produced one, so a connection that worked resets the backoff."""
        capture = self._open()
        if capture is None:
            self._record_error("cannot open RTSP stream")
            return False

        produced = False
        misses = 0
        while not self._stop.is_set():
            ok, image = capture.read()
            if not ok or image is None:
                misses += 1
                if misses >= REOPEN_AFTER_FAILURES:
                    self._record_error("stream stopped yielding frames")
                    return produced
                continue
            misses = 0
            produced = True
            with self._lock:
                self._latest = image
                self._latest_at = time.monotonic()
                self._last_error = ""
            self._frames_seen += 1
        return produced

    def _open(self) -> cv2.VideoCapture | None:
        # Process-global and read by FFMPEG when the capture is constructed,
        # so it is set here rather than at import: a module-level assignment
        # would apply to every VideoCapture the process ever makes.
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = _capture_options(self._timeout_s)
        capture = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
        if not capture.isOpened():
            capture.release()
            return None
        logger.info("rtsp_stream_opened", camera_id=self._camera_id)
        self._capture = capture
        return capture

    def _release(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def _record_error(self, error: str) -> None:
        safe = redact_credentials(error)
        with self._lock:
            self._last_error = safe
        logger.warning("rtsp_stream_failed", camera_id=self._camera_id, error=safe)

    def _fail(self, error: str) -> Frame:
        self._fail_streak += 1
        return failed_frame(self._camera_id, redact_credentials(error))
