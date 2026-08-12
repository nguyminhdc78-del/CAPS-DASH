"""Pulls one fresh frame at a time from an RTSP camera.

WHY IT CONNECTS, GRABS ONE FRAME AND DISCONNECTS, instead of holding the
stream open. Three designs were measured on the board against the reference
camera (640x480 HEVC, 30 fps, over WiFi):

1. Read one frame per worker tick, stream held open. An RTSP capture yields
   frames oldest-first and never skips, so consuming 3 of every 30 leaves the
   other 27 queued. Measured by comparing each frame's presentation timestamp
   against the wall clock: 5.4 s late after 6 s, 28.6 s late after 30 s. The
   lag grew a second per second, without bound.

2. A reader thread draining continuously, keeping only the newest frame. This
   is correct when the network can carry the stream. Here it could not:
   the thread got 1-8 of the 30 frames a second and lag still reached 40 s -
   while the board sat at 0.83 load average, so it was not short of CPU. The
   path to the camera was: 406-1052 ms round trip with 20% packet loss, and
   0.13 Mbit/s actually flowing. TCP collapses under that, the camera keeps
   encoding regardless, and the backlog is on ITS side where no amount of
   draining can reach it.

3. This one. A new RTSP session starts at the live edge, so the first frame
   it delivers is current by construction - there is no queue to inherit,
   because there is no session old enough to have one. Lag is bounded by how
   long a connect takes rather than by how long the process has been running.

The cost is real: a handshake plus a wait for a keyframe, several round trips
on a link where a round trip is half a second. That buys a low frame rate. On
this network the honest choice is a few fresh frames a minute over a smooth
stream of frames from a minute ago - a car park dashboard that is confidently
wrong is worse than one that updates slowly.

If the link is ever fixed, design 2 is the better one and this module should
go back to it; `rtsp_stream_diagnostics.StreamLagTracker` is what tells you
whether the link can sustain it.

TCP, not UDP. UDP would drop rather than queue, which sounds like the fix
here, but a partly decoded frame is not a missing frame - it is a
plausible-looking wrong one, which is exactly what a detector must never be
fed.
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

# How stale a frame may be before `read()` calls the camera down rather than
# serve it. Generous, because one refresh cycle on a bad link is seconds - the
# point is to catch a camera that has stopped, not to police the frame rate.
DEFAULT_MAX_AGE_S = 30.0

# Frames to pull before hanging up. The first decodable frame arrives at a
# keyframe, and a decoder settling in sometimes returns a torn one first.
FRAMES_PER_CONNECTION = 2

INITIAL_BACKOFF_S = 1.0
MAX_BACKOFF_S = 30.0


def _capture_options(timeout_s: float) -> str:
    """FFMPEG options string, `key;value` pairs joined by `|`.

    The timeout bounds how long a connect may hang on a camera that has gone
    away. FFMPEG wants microseconds. Both spellings are passed because the
    option was renamed from `stimeout` to `timeout` and which one a build
    accepts depends on its FFMPEG version; the unrecognised one is ignored.
    """
    micros = max(int(timeout_s * 1_000_000), 1_000_000)
    return f"rtsp_transport;tcp|stimeout;{micros}|timeout;{micros}"


class RtspStreamSource(FrameSource):
    """Refreshes one frame at a time, on a thread, so `read()` never blocks."""

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

        self._lock = threading.Lock()
        self._latest: np.ndarray | None = None
        self._latest_at = 0.0
        self._last_error = "stream has not connected yet"
        self._frames_seen = 0
        self._fail_streak = 0
        self._cycle_ms = 0.0

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
        """Successful refreshes, for diagnostics."""
        return self._frames_seen

    @property
    def cycle_ms(self) -> float:
        """How long the last connect-grab-disconnect took.

        This IS the freshness of the picture: a frame can be no older than one
        cycle, because the session it came from did not exist before that.
        """
        return self._cycle_ms

    def read(self) -> Frame:
        """Newest fetched frame. Never raises - see `base.py`."""
        with self._lock:
            image = self._latest
            age = time.monotonic() - self._latest_at
            error = self._last_error

        if image is None:
            return self._fail(error or "no frame yet")
        if age > self._max_age_s:
            return self._fail(f"camera stalled: newest frame is {age:.1f}s old")

        # Encoded here, not on the refresh thread: this is the frame actually
        # consumed, and the worker may tick faster than the camera refreshes.
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
            # Joined before anything is released: the thread is inside cv2
            # when it blocks, and releasing a VideoCapture another thread is
            # reading is a crash rather than an error. Bounded by the FFMPEG
            # timeout, so shutdown cannot hang on a dead camera.
            thread.join(timeout=self._timeout_s + 2.0)
            if thread.is_alive():
                logger.warning("rtsp_reader_did_not_stop", camera_id=self._camera_id)

    # --- refresh thread ------------------------------------------------------

    def _run(self) -> None:
        backoff = INITIAL_BACKOFF_S
        while not self._stop.is_set():
            started = time.perf_counter()
            try:
                fetched = self._fetch_one()
            except Exception as exc:
                self._record_error(f"{type(exc).__name__}: {exc}")
                fetched = False

            if fetched:
                self._cycle_ms = (time.perf_counter() - started) * 1000.0
                self._frames_seen += 1
                if self._frames_seen % 20 == 1:
                    logger.info(
                        "rtsp_refresh_cycle",
                        camera_id=self._camera_id,
                        cycle_ms=round(self._cycle_ms),
                        refreshes=self._frames_seen,
                    )
                backoff = INITIAL_BACKOFF_S
                # Straight back round: the cycle time is the frame rate, and
                # any pause here is added directly to how old the picture is.
                continue

            if self._stop.wait(backoff):
                return
            backoff = min(backoff * 2, MAX_BACKOFF_S)

    def _fetch_one(self) -> bool:
        """One connect, one frame, one disconnect. True if a frame was stored."""
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = _capture_options(self._timeout_s)
        capture = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
        if not capture.isOpened():
            capture.release()
            self._record_error("cannot open RTSP stream")
            return False

        try:
            image = None
            for _ in range(FRAMES_PER_CONNECTION):
                if self._stop.is_set():
                    return False
                ok, frame = capture.read()
                if ok and frame is not None:
                    image = frame
            if image is None:
                self._record_error("connected but no frame arrived")
                return False

            with self._lock:
                self._latest = image
                self._latest_at = time.monotonic()
                self._last_error = ""
            return True
        finally:
            capture.release()

    def _record_error(self, error: str) -> None:
        safe = redact_credentials(error)
        with self._lock:
            self._last_error = safe
        logger.warning("rtsp_fetch_failed", camera_id=self._camera_id, error=safe)

    def _fail(self, error: str) -> Frame:
        self._fail_streak += 1
        return failed_frame(self._camera_id, redact_credentials(error))
