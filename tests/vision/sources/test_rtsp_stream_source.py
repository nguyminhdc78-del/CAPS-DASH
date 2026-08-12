"""The RTSP source, driven by a stub VideoCapture.

No camera and no network: `cv2.VideoCapture` is replaced with a stub, so the
behaviour that matters - never raising, reopening a dead capture, redacting
credentials - is exercised deterministically. Whether FFMPEG can decode a
given codec is not something a unit test can answer; that was measured on the
board instead and is recorded in the module docstring of the source.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from caps_dash.vision.sources import rtsp_stream_source
from caps_dash.vision.sources.rtsp_stream_source import (
    REOPEN_AFTER_FAILURES,
    RtspStreamSource,
    _capture_options,
)


class StubCapture:
    """Stands in for `cv2.VideoCapture`, scripted per instance."""

    def __init__(self, *, opens: bool = True, reads: list[Any] | None = None) -> None:
        self.opens = opens
        self.reads = reads if reads is not None else []
        self.read_calls = 0
        self.released = False

    def isOpened(self) -> bool:
        """Named for the cv2 API this stands in for, not for PEP 8."""
        return self.opens

    def read(self) -> tuple[bool, Any]:
        self.read_calls += 1
        if not self.reads:
            return False, None
        result = self.reads.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def release(self) -> None:
        self.released = True


def install(monkeypatch: pytest.MonkeyPatch, captures: list[StubCapture]) -> None:
    """Hand out `captures` in order, one per `VideoCapture(...)` construction."""
    queue = list(captures)

    def factory(*_args: object, **_kwargs: object) -> StubCapture:
        return queue.pop(0) if queue else StubCapture(opens=False)

    monkeypatch.setattr(rtsp_stream_source.cv2, "VideoCapture", factory)


def frame(value: int = 120) -> tuple[bool, np.ndarray]:
    return True, np.full((48, 64, 3), value, dtype=np.uint8)


def test_a_good_read_returns_an_image_and_its_jpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, [StubCapture(reads=[frame()])])
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)

    result = source.read()

    assert result.ok
    assert result.image is not None and result.image.shape == (48, 64, 3)
    # Encoded in the source, so the contract stays "bytes out" for every
    # FrameSource regardless of what the camera actually speaks.
    assert result.jpeg_bytes is not None and result.jpeg_bytes.startswith(b"\xff\xd8")
    assert source.fail_streak == 0


def test_read_never_raises_when_the_capture_throws(monkeypatch: pytest.MonkeyPatch) -> None:
    """`base.py` states this in capitals: one broken camera must not take down
    the worker loop that every other camera shares."""
    install(monkeypatch, [StubCapture(reads=[RuntimeError("decoder exploded")])])
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)

    result = source.read()

    assert not result.ok
    assert result.error is not None and "decoder exploded" in result.error


def test_an_unopenable_stream_fails_instead_of_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    capture = StubCapture(opens=False)
    install(monkeypatch, [capture])
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)

    result = source.read()

    assert not result.ok
    assert source.fail_streak == 1
    # An unopened capture is released rather than leaked.
    assert capture.released


def test_the_capture_is_reopened_after_a_run_of_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A camera unplugged and plugged back in leaves `read()` returning False
    forever - the handle stays open, it just never yields another frame."""
    dead = StubCapture(reads=[])
    fresh = StubCapture(reads=[frame()])
    install(monkeypatch, [dead, fresh])
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)

    for _ in range(REOPEN_AFTER_FAILURES):
        assert not source.read().ok
    assert dead.released

    assert source.read().ok
    assert source.fail_streak == 0


def test_credentials_never_reach_the_error_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """`cameras.last_error` is readable by the security role while
    `source_url` is admin-only, so a password must not travel via an error."""
    install(
        monkeypatch,
        [StubCapture(reads=[RuntimeError("failed on rtsp://admin:hunter2@cam/live")])],
    )
    source = RtspStreamSource(1, "rtsp://admin:hunter2@cam/live", 2.0)

    result = source.read()

    assert result.error is not None
    assert "hunter2" not in result.error


def test_transport_is_tcp_and_the_read_cannot_block_forever() -> None:
    """UDP decodes faster but loses packets, and a partly decoded frame is a
    plausible-looking wrong one - the worst possible input to a detector.
    The timeout is what stops a vanished camera pinning the worker thread."""
    options = _capture_options(4.0)

    assert "rtsp_transport;tcp" in options
    assert "stimeout;4000000" in options
    assert "timeout;4000000" in options


def test_a_tiny_timeout_still_leaves_a_usable_floor() -> None:
    """Sub-second values would make a capture that never manages to open."""
    assert "stimeout;1000000" in _capture_options(0.05)


def test_close_releases_the_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    capture = StubCapture(reads=[frame()])
    install(monkeypatch, [capture])
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)
    source.read()

    source.close()

    assert capture.released
