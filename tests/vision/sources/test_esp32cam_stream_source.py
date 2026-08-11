"""The MJPEG stream source, driven by a fake multipart server.

No hardware and no network: an `httpx.MockTransport` plays back a multipart
body, so the parsing rules that matter - partial frames, split chunks, junk
between parts - are exercised deterministically.
"""

from __future__ import annotations

import time

import cv2
import httpx
import numpy as np
import pytest

from caps_dash.vision.sources import esp32cam_stream_source
from caps_dash.vision.sources.esp32cam_stream_source import Esp32CamStreamSource

BOUNDARY = b"--capsframe\r\nContent-Type: image/jpeg\r\n\r\n"


def make_jpeg(width: int = 64, height: int = 48, value: int = 128) -> bytes:
    image = np.full((height, width, 3), value, dtype=np.uint8)
    ok, buffer = cv2.imencode(".jpg", image)
    assert ok
    return bytes(buffer)


def multipart(frames: list[bytes]) -> bytes:
    return b"".join(BOUNDARY + frame + b"\r\n" for frame in frames)


def stream_source(chunks: list[bytes], **kwargs: object) -> Esp32CamStreamSource:
    """A source whose stream yields exactly `chunks`, then ends."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=httpx.ByteStream(b"".join(chunks)))

    transport = httpx.MockTransport(handler)
    original = httpx.Client

    def patched(*args: object, **client_kwargs: object) -> httpx.Client:
        client_kwargs["transport"] = transport
        return original(*args, **client_kwargs)  # type: ignore[arg-type]

    esp32cam_stream_source.httpx.Client = patched  # type: ignore[assignment]
    try:
        return Esp32CamStreamSource(1, "http://camera.invalid/stream", 2.0, **kwargs)  # type: ignore[arg-type]
    finally:
        esp32cam_stream_source.httpx.Client = original  # type: ignore[assignment]


def wait_for_frames(source: Esp32CamStreamSource, count: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while source.frames_seen < count and time.monotonic() < deadline:
        time.sleep(0.02)


def test_the_newest_frame_is_what_read_returns():
    """Latest-wins, like every other part of this pipeline.

    A stream arrives faster than the worker consumes it, so `read()` must hand
    back the current view - not the oldest frame still sitting in a buffer.
    """
    first, second = make_jpeg(value=10), make_jpeg(value=200)
    source = stream_source([multipart([first, second])])
    try:
        wait_for_frames(source, 2)
        frame = source.read()

        assert frame.ok
        assert frame.jpeg_bytes == second
        assert frame.image is not None
    finally:
        source.close()


def test_a_frame_split_across_chunks_is_reassembled():
    """TCP does not respect frame boundaries; the parser must not either."""
    jpeg = make_jpeg()
    body = multipart([jpeg])
    source = stream_source([body[:20], body[20:60], body[60:]])
    try:
        wait_for_frames(source, 1)
        assert source.read().jpeg_bytes == jpeg
    finally:
        source.close()


def test_read_reports_a_failure_before_any_frame_arrives():
    """`read()` never raises and never invents a frame - see `sources/base.py`."""
    source = stream_source([b""])
    try:
        frame = source.read()
        assert frame.ok is False
        assert frame.image is None
        assert source.fail_streak == 1
    finally:
        source.close()


def test_a_stale_stream_is_reported_as_a_failure():
    """A frozen stream must not keep a dead camera looking alive.

    Without the age check the last frame would be served forever and the
    worker's offline detection would never fire.
    """
    source = stream_source([multipart([make_jpeg()])], max_age_s=0.05)
    try:
        wait_for_frames(source, 1)
        time.sleep(0.15)

        frame = source.read()
        assert frame.ok is False
        assert "stalled" in (frame.error or "")
    finally:
        source.close()


def test_junk_between_parts_is_skipped():
    """Header casing and boundary strings vary between firmware builds.

    The parser scans for JPEG markers rather than parsing multipart headers,
    so a firmware that changes either keeps working.
    """
    jpeg = make_jpeg()
    source = stream_source([b"garbage-preamble\r\n" + multipart([jpeg])])
    try:
        wait_for_frames(source, 1)
        assert source.read().jpeg_bytes == jpeg
    finally:
        source.close()


@pytest.mark.parametrize("size", [b"\xff\xd8tiny\xff\xd9"])
def test_frames_outside_the_size_bounds_are_ignored(size: bytes):
    """A 10-byte 'JPEG' is a truncated read, not a picture."""
    source = stream_source([size])
    try:
        time.sleep(0.2)
        assert source.read().ok is False
    finally:
        source.close()
