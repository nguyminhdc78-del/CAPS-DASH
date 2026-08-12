"""The RTSP source, driven by a stub VideoCapture.

No camera and no network: `cv2.VideoCapture` is replaced with a stub, so the
behaviour that matters - a fresh session per frame, never raising, recovering
from a dead camera, redacting credentials - is exercised deterministically.
Whether a given link can carry a stream, and what that costs, is not something
a unit test can answer; that was measured on the board and is recorded in the
module docstring of the source.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import numpy as np
import pytest

from caps_dash.vision.sources import rtsp_stream_source
from caps_dash.vision.sources.rtsp_endpoint_probe import EndpointState, ProbeResult
from caps_dash.vision.sources.rtsp_stream_source import RtspStreamSource, _capture_options


class StubCapture:
    """Stands in for `cv2.VideoCapture`, scripted per instance."""

    def __init__(
        self,
        *,
        opens: bool = True,
        value: int | None = 120,
        raises: Exception | None = None,
    ) -> None:
        self.opens = opens
        self.value = value
        self.raises = raises
        self.released = threading.Event()
        self.reads = 0

    def isOpened(self) -> bool:
        """Named for the cv2 API this stands in for, not for PEP 8."""
        return self.opens

    def read(self) -> tuple[bool, np.ndarray | None]:
        self.reads += 1
        if self.raises is not None:
            raise self.raises
        if self.value is None:
            return False, None
        return True, np.full((48, 64, 3), self.value, dtype=np.uint8)

    def release(self) -> None:
        self.released.set()


def install(
    monkeypatch: pytest.MonkeyPatch,
    make: Callable[[int], StubCapture],
    *,
    endpoint: EndpointState = EndpointState.REACHABLE,
) -> list[StubCapture]:
    """Build a fresh stub per `VideoCapture(...)`; returns the ones created.

    The endpoint probe is stubbed too: it opens a real socket, and a unit test
    must not depend on what `camera.invalid` does on the machine running it.
    """
    created: list[StubCapture] = []
    lock = threading.Lock()

    def factory(*_args: object, **_kwargs: object) -> StubCapture:
        with lock:
            capture = make(len(created))
            created.append(capture)
            return capture

    monkeypatch.setattr(rtsp_stream_source.cv2, "VideoCapture", factory)
    monkeypatch.setattr(
        rtsp_stream_source, "probe", lambda *_a, **_k: ProbeResult(endpoint, str(endpoint))
    )
    return created


def wait_for(predicate: Callable[[], bool], timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_a_good_refresh_returns_an_image_and_its_jpeg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install(monkeypatch, lambda _i: StubCapture(value=120))
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)
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


def test_every_refresh_is_a_new_session_that_is_then_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE design. A new RTSP session starts at the live edge, so its first
    frame is current by construction - there is no queue to inherit because
    there is no session old enough to have built one. Holding one open on
    this link put the picture 40 s behind and growing."""
    created = install(monkeypatch, lambda _i: StubCapture(value=120))
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)
    try:
        assert wait_for(lambda: source.frames_seen >= 3)
        assert len(created) >= 3
        # Every session but possibly the one in flight has been hung up.
        assert all(capture.released.is_set() for capture in created[:-1])
    finally:
        source.close()


def test_the_freshest_value_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, lambda i: StubCapture(value=min(10 + i, 255)))
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)
    try:
        assert wait_for(lambda: source.frames_seen >= 4)
        result = source.read()

        assert result.ok and result.image is not None
        # Later sessions produce higher values; the newest one is served.
        assert int(result.image[0][0][0]) >= 13
    finally:
        source.close()


def test_read_before_any_frame_arrives_fails_rather_than_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install(monkeypatch, lambda _i: StubCapture(opens=False))
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)
    try:
        result = source.read()

        assert not result.ok
        assert source.fail_streak == 1
    finally:
        source.close()


def test_a_connected_camera_that_sends_nothing_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Opening the socket is not the same as the camera streaming; saying so
    beats a frame that never arrives and no explanation."""
    install(monkeypatch, lambda _i: StubCapture(value=None))
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)
    try:
        result = source.read()

        assert not result.ok
        assert wait_for(lambda: "no frame" in (source.read().error or ""))
    finally:
        source.close()


def test_a_stalled_camera_is_reported_not_served_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handing over a frame from minutes ago would keep a dead camera looking
    alive, which is worse than saying the camera is down."""
    install(monkeypatch, lambda _i: StubCapture(value=120))
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0, max_age_s=0.05)
    try:
        assert wait_for(lambda: source.frames_seen >= 1)
        source.close()  # stop refreshing so the frame can go stale
        time.sleep(0.1)

        result = source.read()

        assert not result.ok
        assert result.error is not None and "stalled" in result.error
    finally:
        source.close()


def test_a_thrown_exception_does_not_kill_the_refresher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`base.py` states this in capitals: one broken camera must not take down
    the worker loop that every other camera shares."""
    install(
        monkeypatch,
        lambda i: StubCapture(raises=RuntimeError("decoder exploded"))
        if i == 0
        else StubCapture(value=77),
    )
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)
    try:
        # It caught the failure, backed off, and reconnected on its own.
        assert wait_for(lambda: source.frames_seen >= 1, timeout=8.0)
        assert source.read().ok
    finally:
        source.close()


def test_a_failed_session_is_still_released(monkeypatch: pytest.MonkeyPatch) -> None:
    """A leaked capture per retry would exhaust the board within minutes on a
    camera that is down."""
    created = install(monkeypatch, lambda _i: StubCapture(value=None))
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)
    try:
        assert wait_for(lambda: len(created) >= 1)
        assert wait_for(lambda: created[0].released.is_set())
    finally:
        source.close()


def test_credentials_never_reach_the_error_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """`cameras.last_error` is readable by the security role while
    `source_url` is admin-only, so a password must not travel via an error."""
    install(monkeypatch, lambda _i: StubCapture(opens=False))
    source = RtspStreamSource(1, "rtsp://admin:hunter2@cam/live", 2.0)
    try:
        source._record_error("failed on rtsp://admin:hunter2@cam/live")

        result = source.read()

        assert result.error is not None
        assert "hunter2" not in result.error
    finally:
        source.close()


def test_transport_is_tcp_and_a_connect_cannot_hang_forever() -> None:
    """UDP would drop rather than queue, which sounds like the fix for a bad
    link, but a partly decoded frame is a plausible-looking wrong one - the
    worst possible input to a detector."""
    options = _capture_options(4.0)

    assert "rtsp_transport;tcp" in options
    assert "stimeout;4000000" in options
    assert "timeout;4000000" in options


def test_a_tiny_timeout_still_leaves_a_usable_floor() -> None:
    """Sub-second values would make a capture that never manages to open."""
    assert "stimeout;1000000" in _capture_options(0.05)


def test_close_stops_the_refresher(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, lambda _i: StubCapture(value=120))
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)
    assert wait_for(lambda: source.frames_seen >= 1)

    source.close()
    settled = source.frames_seen
    time.sleep(0.2)

    assert source.frames_seen == settled


def test_a_refused_port_never_reaches_the_decoder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A camera that is on the network but not streaming is answered in
    milliseconds by a TCP connect. Handing that to FFMPEG instead costs the
    full connect timeout and reports it as an indistinguishable failure."""
    created = install(
        monkeypatch, lambda _i: StubCapture(value=120), endpoint=EndpointState.REFUSED
    )
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)
    try:
        result = source.read()

        assert not result.ok
        assert created == []
    finally:
        source.close()
