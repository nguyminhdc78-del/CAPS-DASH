"""The realtime wire format.

    [4 bytes big-endian uint32 = header length N][N bytes UTF-8 JSON][JPEG bytes]

One message carries both the frame and the state that describes it, which is
the whole point. Two separate messages would arrive in order, but a drop under
backpressure could shed one and keep the other - leaving polygons drawn over a
frame they do not describe. A single message cannot desync.

Base64 was the obvious alternative and was rejected: a third more bytes and a
decode step on every frame, for nothing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

HEADER_LENGTH_BYTES = 4

# A header is a few hundred bytes of JSON. Anything past this is either a bug
# or a hostile frame, and must be rejected before allocating for it.
MAX_HEADER_BYTES = 64 * 1024


def encode_frame_message(header: dict[str, Any], jpeg: bytes) -> bytes:
    """Pack a header and a JPEG into one self-framing binary message."""
    encoded = json.dumps(header, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_HEADER_BYTES:
        raise ValueError(f"header too large: {len(encoded)} bytes")
    return len(encoded).to_bytes(HEADER_LENGTH_BYTES, "big") + encoded + jpeg


@dataclass(frozen=True, slots=True)
class FrameMessage:
    header: dict[str, Any]
    jpeg: bytes


def decode_frame_message(message: bytes) -> FrameMessage:
    """Unpack a message. Used by tests and by any Python client."""
    if len(message) < HEADER_LENGTH_BYTES:
        raise ValueError("message shorter than its length prefix")

    header_length = int.from_bytes(message[:HEADER_LENGTH_BYTES], "big")
    if header_length > MAX_HEADER_BYTES:
        raise ValueError(f"declared header length {header_length} exceeds the limit")

    end = HEADER_LENGTH_BYTES + header_length
    if end > len(message):
        raise ValueError("declared header length runs past the end of the message")

    header = json.loads(message[HEADER_LENGTH_BYTES:end].decode("utf-8"))
    return FrameMessage(header=header, jpeg=message[end:])
