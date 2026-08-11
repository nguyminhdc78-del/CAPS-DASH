"""Frame sources.

The rule under test throughout: `read()` never raises. A dead camera returns
`ok=False` so the worker loop keeps serving the other cameras.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import httpx
import numpy as np
import pytest

from caps_dash.vision.sources.esp32cam_http_source import Esp32CamHttpSource
from caps_dash.vision.sources.fake_source import FakeSource
from caps_dash.vision.sources.image_folder_source import ImageFolderSource
from caps_dash.vision.sources.jpeg_utils import decode_jpeg, encode_jpeg


def real_jpeg(width: int = 640, height: int = 480) -> bytes:
    """A JPEG big enough to clear the source's minimum-size check."""
    image = np.random.default_rng(1).integers(0, 255, (height, width, 3), dtype=np.uint8)
    return encode_jpeg(image)


def esp32_source_with(handler) -> Esp32CamHttpSource:
    """An ESP32 source whose HTTP client is backed by a mock transport."""
    source = Esp32CamHttpSource(camera_id=1, url="http://camera.local/anh", timeout_s=1.0)
    source._client = httpx.Client(transport=httpx.MockTransport(handler))
    return source


# --- jpeg_utils --------------------------------------------------------------


def test_decode_returns_none_for_a_truncated_jpeg() -> None:
    """cv2.imdecode returns None WITHOUT raising - the check must be explicit."""
    truncated = real_jpeg()[: 200]
    assert decode_jpeg(truncated) is None


def test_decode_round_trips_a_real_jpeg() -> None:
    image = decode_jpeg(real_jpeg(320, 240))
    assert image is not None
    assert image.shape == (240, 320, 3)


def test_encode_rejects_an_unencodable_array() -> None:
    """A degenerate array must not slip through as empty bytes.

    cv2 raises its own `cv2.error` here rather than returning ok=False, so the
    ValueError guard inside encode_jpeg never fires for this particular input.
    Either way it raises - what matters is that nothing downstream receives a
    zero-length "JPEG" and tries to stream it.
    """
    with pytest.raises(Exception, match=r"(?i)error|failed to encode"):
        encode_jpeg(np.zeros((0, 0, 3), dtype=np.uint8))


def test_encode_honours_the_quality_setting() -> None:
    image = np.random.default_rng(2).integers(0, 255, (240, 320, 3), dtype=np.uint8)
    assert len(encode_jpeg(image, quality=95)) > len(encode_jpeg(image, quality=30))


# --- ESP32-CAM over HTTP -----------------------------------------------------


def test_successful_read_carries_both_the_bytes_and_the_decoded_image() -> None:
    """Both together, so the streamed frame and the inferred frame agree."""
    body = real_jpeg()
    source = esp32_source_with(lambda _request: httpx.Response(200, content=body))

    frame = source.read()

    assert frame.ok
    assert frame.jpeg_bytes == body
    assert frame.image is not None
    assert frame.image.shape == (480, 640, 3)
    assert source.fail_streak == 0


def test_connection_error_returns_a_failed_frame_instead_of_raising() -> None:
    def refuse(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    source = esp32_source_with(refuse)
    frame = source.read()

    assert frame.ok is False
    assert frame.image is None
    assert frame.error is not None


def test_http_error_status_is_a_failure() -> None:
    source = esp32_source_with(lambda _request: httpx.Response(500))
    assert source.read().ok is False


def test_truncated_body_is_a_failure_not_a_crash() -> None:
    """The weak-WiFi case: 200 OK with a body cut short mid-scan."""
    body = real_jpeg()
    truncated = body[: len(body) // 2]
    source = esp32_source_with(lambda _request: httpx.Response(200, content=truncated))

    frame = source.read()
    assert frame.ok is False
    assert "undecodable" in (frame.error or "")


def test_absurdly_small_body_is_rejected_before_decoding() -> None:
    source = esp32_source_with(lambda _request: httpx.Response(200, content=b"nope"))
    frame = source.read()
    assert frame.ok is False
    assert "body size" in (frame.error or "")


def test_fail_streak_counts_up_then_resets_on_success() -> None:
    """What phase 06 compares against to declare a camera offline."""
    responses = [httpx.Response(500), httpx.Response(500), httpx.Response(200, content=real_jpeg())]
    source = esp32_source_with(lambda _request: responses.pop(0))

    source.read()
    assert source.fail_streak == 1
    source.read()
    assert source.fail_streak == 2
    source.read()
    assert source.fail_streak == 0


# --- Hardware-free sources ---------------------------------------------------


def test_fake_source_produces_a_usable_frame() -> None:
    """No hardware, no model, no files - CI depends on this working."""
    frame = FakeSource(camera_id=7).read()

    assert frame.ok
    assert frame.camera_id == 7
    assert frame.image is not None
    assert frame.jpeg_bytes is not None
    # The bytes must actually decode; a placeholder that is not real JPEG
    # would break the realtime channel, which forwards them untouched.
    assert decode_jpeg(frame.jpeg_bytes) is not None


def test_image_folder_source_cycles_through_the_directory(tmp_path: Path) -> None:
    for index in range(2):
        image = np.full((48, 64, 3), index * 100, dtype=np.uint8)
        cv2.imwrite(str(tmp_path / f"frame-{index}.jpg"), image)

    source = ImageFolderSource(camera_id=1, directory=tmp_path)
    first, second, third = source.read(), source.read(), source.read()

    assert all(frame.ok for frame in (first, second, third))
    # Looped back to the start rather than running out.
    assert third.jpeg_bytes == first.jpeg_bytes
    assert second.jpeg_bytes != first.jpeg_bytes


def test_image_folder_source_fails_cleanly_on_an_empty_directory(tmp_path: Path) -> None:
    frame = ImageFolderSource(camera_id=1, directory=tmp_path).read()
    assert frame.ok is False


def test_image_folder_source_fails_cleanly_on_a_missing_directory(tmp_path: Path) -> None:
    frame = ImageFolderSource(camera_id=1, directory=tmp_path / "nope").read()
    assert frame.ok is False
