"""Holds an MJPEG stream open and hands out the newest frame on demand.

WHY, measured on the real hardware: one still over HTTP costs ~74 ms - 8 ms
TCP handshake, 37 ms of sensor capture and JPEG encode, 28 ms to move 12.8 KB
over WiFi - and those run strictly in sequence, capping a polling source at
about 13 fps. Worse, that 74 ms is spent *inside* `read()`, so every camera
tick waits on the network before any work starts.

A stream removes the handshake and lets the sensor capture the next frame
while the current one is still being sent, so `read()` becomes a memory
lookup and the tick starts working immediately.

**The frame is not decoded here.** A reader thread that decoded every frame
would burn roughly 70 ms of CPU per frame - at 25 fps that is more CPU than
the board has, spent on frames nobody asked for. The thread keeps the raw
JPEG; `read()` decodes exactly the frames the worker actually consumes.
"""

from __future__ import annotations

import threading
import time

import httpx

from ...db.types import utc_now
from ...observability.credential_redaction import redact_credentials
from ...observability.logging_setup import get_logger
from .base import Frame, FrameSource, failed_frame
from .jpeg_utils import decode_jpeg

logger = get_logger(__name__)

MIN_BODY_BYTES = 512
MAX_BODY_BYTES = 2_000_000

# A frame older than this is not "the current view" any more, so `read()`
# reports a failure instead of handing the worker a stale picture that would
# keep a dead camera looking alive.
DEFAULT_MAX_AGE_S = 5.0

INITIAL_BACKOFF_S = 1.0
MAX_BACKOFF_S = 30.0


class Esp32CamStreamSource(FrameSource):
    """One long-lived MJPEG connection per camera, drained by a background thread."""

    def __init__(
        self,
        camera_id: int,
        url: str,
        timeout_s: float,
        *,
        max_age_s: float = DEFAULT_MAX_AGE_S,
    ) -> None:
        self._camera_id = camera_id
        self._url = url
        self._timeout_s = timeout_s
        self._max_age_s = max_age_s

        self._lock = threading.Lock()
        self._latest: bytes | None = None
        self._latest_at = 0.0
        self._last_error = "stream has not connected yet"
        self._frames_seen = 0
        self._fail_streak = 0

        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name=f"mjpeg-{camera_id}", daemon=True
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
        """Frames the reader thread has taken off the wire, for diagnostics."""
        return self._frames_seen

    def read(self) -> Frame:
        """Newest frame from the stream. Never raises - see `base.py`."""
        with self._lock:
            jpeg = self._latest
            age = time.monotonic() - self._latest_at
            error = self._last_error

        if jpeg is None:
            return self._fail(error)
        if age > self._max_age_s:
            return self._fail(f"stream stalled: newest frame is {age:.1f}s old")

        image = decode_jpeg(jpeg)
        if image is None:
            return self._fail("undecodable JPEG from stream")

        self._fail_streak = 0
        return Frame(
            camera_id=self._camera_id,
            timestamp=utc_now(),
            image=image,
            jpeg_bytes=jpeg,
            ok=True,
        )

    def close(self) -> None:
        self._stop.set()
        # Not joined: the thread is blocked reading a socket that only closes
        # when the client goes away, and shutdown must not wait on a camera
        # that has stopped answering. It is a daemon, and it checks `_stop`
        # between frames.
        self._thread = None  # type: ignore[assignment]

    # --- reader thread -------------------------------------------------------

    def _run(self) -> None:
        backoff = INITIAL_BACKOFF_S
        while not self._stop.is_set():
            try:
                self._consume_stream()
                backoff = INITIAL_BACKOFF_S
            except Exception as exc:
                self._record_error(f"{type(exc).__name__}: {exc}")
                if self._stop.wait(backoff):
                    return
                backoff = min(backoff * 2, MAX_BACKOFF_S)

    def _consume_stream(self) -> None:
        # `read` timeout only, no total timeout: the whole point is a
        # connection that stays open indefinitely.
        timeout = httpx.Timeout(self._timeout_s, read=self._timeout_s, pool=None)
        with httpx.Client(timeout=timeout) as client, client.stream("GET", self._url) as response:
            response.raise_for_status()
            logger.info("mjpeg_stream_opened", camera_id=self._camera_id)
            buffer = bytearray()
            for chunk in response.iter_bytes():
                if self._stop.is_set():
                    return
                buffer.extend(chunk)
                self._extract_frames(buffer)
                if len(buffer) > MAX_BODY_BYTES * 2:
                    # No JPEG start marker in a buffer this large means the
                    # peer is not sending MJPEG at all. Drop it rather than
                    # growing until the board runs out of memory.
                    buffer.clear()
                    self._record_error("no JPEG markers in stream; dropping buffer")

    def _extract_frames(self, buffer: bytearray) -> None:
        """Pull every complete JPEG out of the buffer, keeping only the newest.

        Boundary-agnostic on purpose: it scans for the JPEG SOI/EOI markers
        rather than parsing multipart headers, so a firmware that changes its
        boundary string or its header casing keeps working.
        """
        while True:
            start = buffer.find(b"\xff\xd8")
            if start < 0:
                return
            end = buffer.find(b"\xff\xd9", start + 2)
            if end < 0:
                del buffer[:start]  # keep the partial frame, drop what precedes it
                return

            jpeg = bytes(buffer[start : end + 2])
            del buffer[: end + 2]
            if MIN_BODY_BYTES <= len(jpeg) <= MAX_BODY_BYTES:
                with self._lock:
                    self._latest = jpeg
                    self._latest_at = time.monotonic()
                    self._last_error = ""
                self._frames_seen += 1

    def _record_error(self, error: str) -> None:
        safe = redact_credentials(error)
        with self._lock:
            self._last_error = safe
        logger.warning("mjpeg_stream_failed", camera_id=self._camera_id, error=safe)

    def _fail(self, error: str) -> Frame:
        self._fail_streak += 1
        return failed_frame(self._camera_id, error)
