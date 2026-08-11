"""JPEG encode/decode with the explicit truncation check ESP32 sources need.

`cv2.imdecode` returns `None` on a bad buffer WITHOUT raising - this module
is the one place that check happens, so every frame source gets it for free
instead of one of them forgetting it three months from now.
"""

from __future__ import annotations

import cv2
import numpy as np


def decode_jpeg(data: bytes) -> np.ndarray | None:
    """Decode JPEG bytes to a BGR array, or `None` if truncated/corrupt.

    A weak-WiFi ESP32-CAM can serve a 200 OK with a body cut short mid-scan.
    `cv2.imdecode` silently returns `None` for that instead of raising - the
    caller MUST check for it explicitly, which is exactly what every source
    in this package does before trusting the result.
    """
    buffer = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(buffer, cv2.IMREAD_COLOR)


def encode_jpeg(image: np.ndarray, quality: int = 85) -> bytes:
    """Encode a BGR array to JPEG bytes, for sources that only have decoded frames."""
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("cv2 failed to encode frame as JPEG")
    return buffer.tobytes()
