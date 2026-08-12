"""The RTSP source, driven by a stub VideoCapture.

No camera and no network: `cv2.VideoCapture` and the endpoint probe are both
replaced, so the behaviour that matters - one session serving many frames,
resyncing when the picture falls behind, never raising, redacting credentials
- is exercised deterministically. What a real link costs is not something a
unit test can answer; that was measured on the board and is recorded in the
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

# Frames the lag tracker needs before it reports; the stub delivers them fast,
# so this only has to match the source's own default.
FRAMES_PER_LAG_REPORT = 150


class StubCapture:
    """Stands in for `cv2.VideoCapture`, scripted per instance.

    `pts_step_ms` is how fast the stream's own clock advances per frame. Set
    it below real time and the source sees the picture falling behind, which
    is the condition a resync exists for.
    """

    def __init__(
        self,
        *,
        opens: bool = True,
        value: int | None = 120,
        raises: Exception | None = None,
        pts_step_ms: float = 1000.0,
    ) -> None:
        self.opens = opens
        self.value = value
        self.raises = raises
        self.pts_step_ms = pts_step_ms
        self.released = threading.Event()
        self.reads = 0
        self._pts_ms = 0.0

    def isOpened(self) -> bool:
        """Named for the cv2 API this stands in for, not for PEP 8."""
        return self.opens

    def read(self) -> tuple[bool, np.ndarray | None]:
        self.reads += 1
        if self.raises is not None:
            raise self.raises
        if self.value is None:
            return False, None
        self._pts_ms += self.pts_step_ms
        # Pace the reader so a test can make assertions without it spinning a
        # core on an infinite supply of frames.
        time.sleep(0.001)
        brightness = min(self.value + self.reads, 255)
        return True, np.full((48, 64, 3), brightness, dtype=np.uint8)

    def get(self, _prop: int) -> float:
        """Only CAP_PROP_POS_MSEC is asked for - the lag tracker's input."""
        return self._pts_ms

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


def wait_for(predicate: Callable[[], bool], timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_a_good_read_returns_an_image_and_its_jpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, lambda _i: StubCapture())
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


def test_one_session_serves_many_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    """THE constraint. A session per frame bounded the lag nicely and opened
    about twenty RTSP sessions a minute, until the camera's session table gave
    out and FFMPEG began reporting `method PLAY failed: 454 Session Not
    Found` - the server handing out an id and immediately forgetting it."""
    created = install(monkeypatch, lambda _i: StubCapture())
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)
    try:
        assert wait_for(lambda: source.frames_seen >= 50)

        assert len(created) == 1
        assert created[0].reads >= 50
    finally:
        source.close()


def test_the_newest_frame_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    """An RTSP capture yields frames oldest-first and never skips, so without
    a draining thread the worker is handed the oldest queued frame and falls a
    second further behind every second."""
    install(monkeypatch, lambda _i: StubCapture(value=0))
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)
    try:
        assert wait_for(lambda: source.frames_seen >= 20)
        first = source.read()
        assert wait_for(lambda: source.frames_seen >= 60)
        second = source.read()

        assert first.image is not None and second.image is not None
        # The stub brightens by one level per frame, so a later read must be
        # strictly brighter - it cannot have been served a queued older frame.
        assert int(second.image[0][0][0]) > int(first.image[0][0][0])
    finally:
        source.close()


def test_the_session_is_rebuilt_when_the_picture_falls_behind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Draining keeps up only while the link can carry the stream. When it
    cannot, the backlog sits on the camera's side of the connection where
    nothing this end can discard it, and reconnecting is the only way back to
    the live edge."""
    # The stream clock crawls, so wall time runs away from it immediately.
    created = install(monkeypatch, lambda _i: StubCapture(pts_step_ms=0.1))
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0, resync_lag_s=0.05)
    try:
        assert wait_for(lambda: source.resyncs >= 1, timeout=20.0)

        # A rebuild means a second session, and the first one hung up.
        assert wait_for(lambda: len(created) >= 2, timeout=10.0)
        assert created[0].released.is_set()
    finally:
        source.close()


def test_a_healthy_stream_is_never_rebuilt(monkeypatch: pytest.MonkeyPatch) -> None:
    """The other half: a reconnect costs a handshake and a wait for a
    keyframe, and doing it routinely is what wore the camera down."""
    # The stream clock runs ahead of wall time, so the reader is never behind.
    install(monkeypatch, lambda _i: StubCapture(pts_step_ms=5000.0))
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0, resync_lag_s=1.0)
    try:
        assert wait_for(lambda: source.frames_seen >= FRAMES_PER_LAG_REPORT + 5, timeout=20.0)

        assert source.resyncs == 0
    finally:
        source.close()


def test_a_frame_already_encoded_is_not_encoded_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker may tick faster than the camera produces. Encoding on every
    read made an unchanged frame pay 6.5 ms of JPEG over and over; encoding
    every decoded frame instead would spend a fifth of a core on frames nobody
    consumes. Cached by sequence number, it does neither."""
    # One frame then nothing, so the sequence number cannot move underneath
    # the assertion.
    install(monkeypatch, lambda _i: StubCapture(value=None) if _i else StubCapture())
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)
    try:
        assert wait_for(lambda: source.frames_seen >= 1)
        source.close()  # freeze the reader; the stored frame stops changing

        first = source.read()
        second = source.read()

        assert first.jpeg_bytes is not None
        # Same object, not merely equal bytes: it was reused, not rebuilt.
        assert second.jpeg_bytes is first.jpeg_bytes
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


def test_a_reachable_port_that_will_not_open_says_so_precisely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Measured on the reference camera: a raw DESCRIBE returned 200 OK while
    FFMPEG failed the same connection with `454 Session Not Found`. "Cannot
    open RTSP stream" sends the operator to look at the network, which was
    healthy at 24 ms with no packet loss."""
    install(monkeypatch, lambda _i: StubCapture(opens=False))
    source = RtspStreamSource(1, "rtsp://cam.local:8554/live", 2.0)
    try:
        assert wait_for(lambda: "not answering RTSP" in (source.read().error or ""))
        assert "cam.local:8554" in (source.read().error or "")
    finally:
        source.close()


def test_a_stalled_stream_is_reported_not_served_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handing over a frame from minutes ago would keep a dead camera looking
    alive, which is worse than saying the camera is down."""
    install(monkeypatch, lambda _i: StubCapture())
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0, max_age_s=0.05)
    try:
        assert wait_for(lambda: source.frames_seen >= 1)
        source.close()  # stop the reader so the frame can go stale
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
    install(
        monkeypatch,
        lambda i: StubCapture(raises=RuntimeError("decoder exploded"))
        if i == 0
        else StubCapture(),
    )
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)
    try:
        # It caught the failure, backed off, and reconnected on its own.
        assert wait_for(lambda: source.frames_seen >= 1, timeout=10.0)
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
    """UDP drops rather than queues, which sounds like the fix for a lossy
    link, but a partly decoded frame is a plausible-looking wrong one - the
    worst possible input to a detector."""
    options = _capture_options(4.0)

    assert "rtsp_transport;tcp" in options
    assert "stimeout;4000000" in options
    assert "timeout;4000000" in options


def test_a_tiny_timeout_still_leaves_a_usable_floor() -> None:
    """Sub-second values would make a capture that never manages to open."""
    assert "stimeout;1000000" in _capture_options(0.05)


def test_close_stops_the_reader_and_releases_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Released only after the reader has been joined: releasing a capture a
    live thread is reading is a crash, not an error."""
    created = install(monkeypatch, lambda _i: StubCapture())
    source = RtspStreamSource(1, "rtsp://camera.invalid/live", 2.0)
    assert wait_for(lambda: source.frames_seen >= 1)

    source.close()

    assert created[0].released.is_set()
