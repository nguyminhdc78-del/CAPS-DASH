"""The RTSP source, driven by a stub VideoCapture.

No camera and no network: `cv2.VideoCapture` is replaced with a stub, so the
behaviour that matters - keeping the newest frame, never raising, reopening a
dead capture, redacting credentials - is exercised deterministically. Whether
FFMPEG can decode a given codec, and what that costs, is not something a unit
test can answer; that was measured on the board and is recorded in the
module docstring of the source.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import numpy as np
import pytest

from caps_dash.vision.sources import rtsp_stream_source
from caps_dash.vision.sources.rtsp_stream_source import RtspStreamSource, _capture_options


class StubCapture:
    """Stands in for `cv2.VideoCapture`, scripted per instance."""

    def __init__(self, *, opens: bool = True, reads: list[Any] | None = None) -> None:
        self.opens = opens
        self._reads = list(reads or [])
        self.released = threading.Event()

    def isOpened(self) -> bool:
        """Named for the cv2 API this stands in for, not for PEP 8."""
        return self.opens

    def read(self) -> tuple[bool, Any]:
        if not self._reads:
            # Exhausted: pace the reader thread instead of letting it spin a
            # core while the test makes its assertions.
            time.sleep(0.01)
            return False, None
        result = self._reads.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def release(self) -> None:
        self.released.set()


def install(monkeypatch: pytest.MonkeyPatch, captures: list[StubCapture]) -> None:
    """Hand out `captures` in order, one per `VideoCapture(...)` construction."""
    queue = list(captures)
    lock = threading.Lock()

    def factory(*_args: object, **_kwargs: object) -> StubCapture:
        with lock:
            return queue.pop(0) if queue else StubCapture(opens=False)

    monkeypatch.setattr(rtsp_stream_source.cv2, "VideoCapture", factory)


def frame(value: int) -> tuple[bool, np.ndarray]:
    return True, np.full((48, 64, 3), value, dtype=np.uint8)


def wait_for(predicate: Any, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def source_for(monkeypatch: pytest.MonkeyPatch, captures: list[StubCapture]) -> RtspStreamSource:
    install(monkeypatch, captures)
    return RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)


def test_a_good_read_returns_an_image_and_its_jpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    source = source_for(monkeypatch, [StubCapture(reads=[frame(120)])])
    try:
        assert wait_for(lambda: source.frames_seen >= 1)
        result = source.read()

        assert result.ok
        assert result.image is not None and result.image.shape == (48, 64, 3)
        # Encoded in the source, so the contract stays "bytes out" for every
        # FrameSource regardless of what the camera actually speaks.
        assert result.jpeg_bytes is not None and result.jpeg_bytes.startswith(b"\xff\xd8")
        assert source.fail_streak == 0
    finally:
        source.close()


def test_the_newest_frame_wins_not_the_oldest(monkeypatch: pytest.MonkeyPatch) -> None:
    """THE reason this source has a reader thread. An RTSP capture yields
    frames oldest-first and never skips, so a worker reading a few times a
    second falls one second further behind per second - measured at 28.6 s
    of lag after 30 s of running before the thread existed."""
    frames = [frame(value) for value in range(10, 60)]
    source = source_for(monkeypatch, [StubCapture(reads=frames)])
    try:
        assert wait_for(lambda: source.frames_seen >= 50)
        result = source.read()

        assert result.ok
        assert result.image is not None
        # The last frame fed in, not the first.
        assert int(result.image[0][0][0]) == 59
    finally:
        source.close()


def test_read_before_any_frame_arrives_fails_rather_than_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = source_for(monkeypatch, [StubCapture(opens=False)])
    try:
        result = source.read()

        assert not result.ok
        assert source.fail_streak == 1
    finally:
        source.close()


def test_a_stalled_stream_is_reported_not_served_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handing over a frame from minutes ago would keep a dead camera looking
    alive, which is worse than saying the camera is down."""
    install(monkeypatch, [StubCapture(reads=[frame(120)])])
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0, max_age_s=0.05)
    try:
        assert wait_for(lambda: source.frames_seen >= 1)
        time.sleep(0.1)

        result = source.read()

        assert not result.ok
        assert result.error is not None and "stalled" in result.error
    finally:
        source.close()


def test_a_thrown_exception_does_not_kill_the_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`base.py` states this in capitals: one broken camera must not take down
    the worker loop that every other camera shares."""
    dead = StubCapture(reads=[RuntimeError("decoder exploded")])
    fresh = StubCapture(reads=[frame(77)])
    source = source_for(monkeypatch, [dead, fresh])
    try:
        # The thread caught it, backed off, and reconnected on its own.
        assert wait_for(lambda: source.frames_seen >= 1, timeout=8.0)
        assert source.read().ok
    finally:
        source.close()


def test_credentials_never_reach_the_error_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """`cameras.last_error` is readable by the security role while
    `source_url` is admin-only, so a password must not travel via an error."""
    install(monkeypatch, [StubCapture(opens=False)])
    source = RtspStreamSource(1, "rtsp://admin:hunter2@cam/live", 2.0)
    try:
        source._record_error("failed on rtsp://admin:hunter2@cam/live")

        result = source.read()

        assert result.error is not None
        assert "hunter2" not in result.error
    finally:
        source.close()


def test_transport_is_tcp_and_the_read_cannot_block_forever() -> None:
    """UDP decodes faster but loses packets, and a partly decoded frame is a
    plausible-looking wrong one - the worst possible input to a detector.
    The timeout is what stops a vanished camera pinning the reader thread."""
    options = _capture_options(4.0)

    assert "rtsp_transport;tcp" in options
    assert "stimeout;4000000" in options
    assert "timeout;4000000" in options


def test_a_tiny_timeout_still_leaves_a_usable_floor() -> None:
    """Sub-second values would make a capture that never manages to open."""
    assert "stimeout;1000000" in _capture_options(0.05)


def test_close_stops_the_reader_and_releases_the_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Released only after the reader has been joined: releasing a capture a
    live thread is reading is a crash, not an error."""
    capture = StubCapture(reads=[frame(120)])
    source = source_for(monkeypatch, [capture])
    assert wait_for(lambda: source.frames_seen >= 1)

    source.close()

    assert capture.released.is_set()
