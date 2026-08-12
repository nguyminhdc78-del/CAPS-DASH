"""Reads an RTSP camera through OpenCV's FFMPEG backend.

ONE session, held open and drained by a reader thread, reconnected only when
the picture actually falls behind. Every part of that sentence was arrived at
by measurement on the board, against the reference camera (640x480 HEVC at
30 fps), and the discarded designs are recorded because each looks reasonable
until it is measured.

**Why a reader thread.** An RTSP capture yields frames oldest-first and never
skips. A worker ticking every 0.3 s consumes 3 of the 30 frames a second and
leaves 27 queued, so the picture falls behind by a second per second, without
bound - measured against each frame's own presentation timestamp:

    after  5.8 s of real time, the frame shown was from  0.4 s  ->  5.4 s late
    after 30.4 s of real time, the frame shown was from  1.8 s  -> 28.6 s late

The thread drains at the rate the camera sends, so `read()` becomes a memory
lookup and the newest frame is always the one on offer. It costs 17 ms a
frame here - about half a core at 30 fps - and `grab()` was measured as a
cheaper drain that skips the BGR conversion; at 19.2 ms it is not cheaper at
all, so the thread simply reads.

**Why NOT a session per frame.** Connecting, taking one frame and hanging up
bounds the lag by construction: a new session starts at the live edge, so it
cannot inherit a queue. It worked, at about 3.1 s a frame. It also opened
roughly twenty RTSP sessions a minute, and this camera's session table could
not take it - FFMPEG eventually reported

    method PLAY failed: 454 Session Not Found

which is the server handing out a session id and immediately forgetting it. A
raw DESCRIBE still returned 200 OK at the time, so the camera was reachable
and talking; it had simply been worn down. One long-lived session cannot do
that.

**Why a resync threshold rather than nothing.** Draining continuously only
keeps up while the link can carry the stream. It once could not - 406-1052 ms
round trip, 20% packet loss, 0.13 Mbit/s flowing - and the reader got 1-8 of
the 30 frames a second while the board sat at 0.83 load average, so it was
not short of CPU. TCP collapses under that loss, the camera keeps encoding
regardless, and the backlog is on ITS side where draining cannot reach it.
That link was later measured at 24 ms with no loss, so the condition is
transient rather than a property of this installation - which is exactly why
it is handled automatically instead of designed around. When
`StreamLagTracker` reports the picture more than `RESYNC_LAG_S` behind, the
session is torn down and rebuilt once, which puts it back at the live edge.

TCP, not UDP. UDP drops rather than queues, which sounds like the fix for a
lossy link, but a partly decoded frame is not a missing frame - it is a
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
from .rtsp_endpoint_probe import EndpointState, endpoint_label, probe
from .rtsp_stream_diagnostics import StreamLagTracker

logger = get_logger(__name__)

DEFAULT_JPEG_QUALITY = 85

# A frame older than this is not "the current view" any more, so `read()`
# reports a failure instead of handing the worker a stale picture that would
# keep a dead camera looking alive.
DEFAULT_MAX_AGE_S = 5.0

# How far behind real time the picture may drift before the session is rebuilt.
# Generous enough that a healthy link never triggers it - a reconnect costs a
# handshake and a wait for a keyframe - and tight enough that a car park is
# never shown as it was ten seconds ago.
RESYNC_LAG_S = 3.0

INITIAL_BACKOFF_S = 1.0
MAX_BACKOFF_S = 30.0

# Retry gap while the camera is reachable but not serving. Short on purpose:
# the check costs milliseconds and the answer can change the moment an
# operator presses a button on the camera.
IDLE_RETRY_S = 2.0


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
    """One long-lived RTSP session per camera, drained by a background thread."""

    def __init__(
        self,
        camera_id: int,
        url: str,
        timeout_s: float,
        *,
        jpeg_quality: int = DEFAULT_JPEG_QUALITY,
        max_age_s: float = DEFAULT_MAX_AGE_S,
        resync_lag_s: float = RESYNC_LAG_S,
    ) -> None:
        self._camera_id = camera_id
        self._url = url
        self._timeout_s = timeout_s
        self._jpeg_quality = jpeg_quality
        self._max_age_s = max_age_s
        self._resync_lag_s = resync_lag_s

        self._capture: cv2.VideoCapture | None = None

        self._lock = threading.Lock()
        self._latest: np.ndarray | None = None
        self._latest_at = 0.0
        self._latest_seq = 0
        self._last_error = "stream has not connected yet"
        self._frames_seen = 0
        self._fail_streak = 0
        self._resyncs = 0

        # Encoding is deferred to `read()` - the thread decodes 30 frames a
        # second and the worker consumes a few, so encoding them all would
        # spend a fifth of a core on frames nobody sees - but cached by
        # sequence number, so a worker ticking faster than the camera does not
        # re-encode a frame it has already been given.
        self._encoded_seq = -1
        self._encoded: bytes | None = None

        self._lag = StreamLagTracker()
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

    @property
    def resyncs(self) -> int:
        """Times the session was rebuilt because the picture fell behind."""
        return self._resyncs

    def read(self) -> Frame:
        """Newest decoded frame. Never raises - see `base.py`."""
        with self._lock:
            image = self._latest
            seq = self._latest_seq
            age = time.monotonic() - self._latest_at
            error = self._last_error

        if image is None:
            return self._fail(error or "no frame yet")
        if age > self._max_age_s:
            return self._fail(f"stream stalled: newest frame is {age:.1f}s old")

        if seq != self._encoded_seq or self._encoded is None:
            self._encoded = encode_jpeg(image, self._jpeg_quality)
            self._encoded_seq = seq

        self._fail_streak = 0
        return Frame(
            camera_id=self._camera_id,
            timestamp=utc_now(),
            image=image,
            jpeg_bytes=self._encoded,
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
                return
        self._release()

    # --- reader thread -------------------------------------------------------

    def _run(self) -> None:
        backoff = INITIAL_BACKOFF_S
        while not self._stop.is_set():
            reachable = probe(self._url, min(self._timeout_s, 2.0))
            if reachable.state is not EndpointState.REACHABLE:
                self._record_error(reachable.detail)
                wait = IDLE_RETRY_S if reachable.worth_retrying_soon else backoff
                if self._stop.wait(wait):
                    return
                if not reachable.worth_retrying_soon:
                    backoff = min(backoff * 2, MAX_BACKOFF_S)
                continue

            try:
                produced = self._drain()
            except Exception as exc:
                self._record_error(f"{type(exc).__name__}: {exc}")
                produced = False
            finally:
                self._release()

            if produced:
                backoff = INITIAL_BACKOFF_S
                continue
            if self._stop.wait(backoff):
                return
            backoff = min(backoff * 2, MAX_BACKOFF_S)

    def _drain(self) -> bool:
        """Hold one session open, keeping the newest frame.

        Returns True if it ever produced a frame, so a session that worked
        resets the backoff even when it ends by falling behind.
        """
        capture = self._open()
        if capture is None:
            self._record_error(
                f"camera at {endpoint_label(self._url)} accepts connections but is "
                "not answering RTSP - restart the stream on the camera"
            )
            return False

        produced = False
        self._lag.reset()  # a new session is a new timeline
        while not self._stop.is_set():
            ok, image = capture.read()
            if not ok or image is None:
                self._record_error("stream stopped yielding frames")
                return produced

            produced = True
            with self._lock:
                self._latest = image
                self._latest_at = time.monotonic()
                self._latest_seq += 1
                self._last_error = ""
            self._frames_seen += 1

            if self._behind(capture):
                return produced
        return produced

    def _behind(self, capture: cv2.VideoCapture) -> bool:
        """Whether the picture has drifted far enough to be worth rebuilding.

        Reconnecting is the only way back to the live edge: the queue is on
        the camera's side of a TCP connection, so nothing this end can discard
        it. The cost is a handshake, which is why this is a threshold rather
        than something done routinely - a session per frame is what wore the
        camera's session table down to `454 Session Not Found`.
        """
        report = self._lag.note_frame(capture.get(cv2.CAP_PROP_POS_MSEC))
        if report is None:
            return False

        logger.info(
            "rtsp_stream_lag",
            camera_id=self._camera_id,
            decode_fps=round(report.decode_fps, 1),
            lag_s=round(report.lag_s, 2),
            lag_growth_s=round(report.lag_growth_s, 2),
        )
        if report.lag_s <= self._resync_lag_s:
            return False

        self._resyncs += 1
        logger.warning(
            "rtsp_stream_resync",
            camera_id=self._camera_id,
            lag_s=round(report.lag_s, 2),
            resyncs=self._resyncs,
        )
        return True

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
