"""The wire format survives the sizes it will actually meet."""

from __future__ import annotations

import json

import pytest

from caps_dash.realtime.frame_protocol import (
    HEADER_LENGTH_BYTES,
    MAX_HEADER_BYTES,
    decode_frame_message,
    encode_frame_message,
)


def test_roundtrip_preserves_header_and_jpeg():
    header = {"camera_id": 1, "seq": 7, "slots": [{"code": "A1", "state": "FREE"}]}
    jpeg = b"\xff\xd8\xff" + b"payload" * 100

    decoded = decode_frame_message(encode_frame_message(header, jpeg))

    assert decoded.header == header
    assert decoded.jpeg == jpeg


def test_empty_jpeg_roundtrips():
    """A frame with no image is malformed upstream, not a decoder crash here."""
    decoded = decode_frame_message(encode_frame_message({"seq": 1}, b""))
    assert decoded.jpeg == b""


def test_one_megabyte_jpeg_roundtrips():
    jpeg = bytes(1024 * 1024)
    decoded = decode_frame_message(encode_frame_message({"seq": 2}, jpeg))
    assert len(decoded.jpeg) == len(jpeg)


def test_oversized_header_is_refused_on_encode():
    with pytest.raises(ValueError, match="header too large"):
        encode_frame_message({"junk": "x" * (MAX_HEADER_BYTES + 1)}, b"")


def test_declared_length_past_the_end_is_refused():
    """A hostile prefix must not make the decoder read past the buffer."""
    # Inside the size limit, so it gets past the first guard - this is the
    # case a naive slice would silently accept, returning a short header.
    message = (1000).to_bytes(HEADER_LENGTH_BYTES, "big") + b'{"seq":1}'
    with pytest.raises(ValueError, match="runs past the end"):
        decode_frame_message(message)


def test_declared_length_beyond_the_limit_is_refused():
    message = (MAX_HEADER_BYTES + 1).to_bytes(HEADER_LENGTH_BYTES, "big") + b"{}"
    with pytest.raises(ValueError, match="exceeds the limit"):
        decode_frame_message(message)


def test_truncated_message_is_refused():
    with pytest.raises(ValueError, match="shorter than its length prefix"):
        decode_frame_message(b"\x00\x00")


def test_typical_header_stays_small():
    """Header size is per-frame overhead, so it is worth watching.

    Six slots with quadrilateral polygons plus a handful of detections is what
    one ceiling camera actually produces. If this ever approaches the 8 KB
    warning threshold, something is putting site-wide data on every frame.
    """
    header = {
        "camera_id": 1,
        "camera_code": "C1",
        "seq": 1,
        "captured_at": "2026-08-11T12:00:00+00:00",
        "frame_w": 1600,
        "frame_h": 900,
        "process_ms": 42.1,
        "confidence": 0.25,
        "slots": [
            {
                "code": f"A{index}",
                "state": "OCCUPIED",
                "polygon": [[100.0, 100.0], [200.0, 100.0], [200.0, 200.0], [100.0, 200.0]],
            }
            for index in range(6)
        ],
        "detections": [
            {"x1": 1.0, "y1": 2.0, "x2": 3.0, "y2": 4.0, "confidence": 0.9, "label": "car"}
            for _ in range(6)
        ],
    }
    assert len(json.dumps(header, separators=(",", ":")).encode()) < 2048
