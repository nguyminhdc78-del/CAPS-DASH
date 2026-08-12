"""Pulls a JPEG snapshot over HTTP from any device serving one still per GET.

The contract is the whole interface: one request, one complete JPEG, a few KB
at 640x480, polled every 1-3 s. Two devices satisfy it here - the MaixCam
running `deploy/maixcam/http_snapshot_main.py` on the USB-C link, which is the
primary path, and an ESP32-CAM serving `GET /anh`, which is where the type is
named after and still works.

A body can arrive truncated while the HTTP layer still reports 200 OK - the
original case was weak basement WiFi, and it stays possible on any link that
can drop a connection mid-response. See `jpeg_utils.decode_jpeg` for the
explicit check that catches it.
"""

from __future__ import annotations

import httpx

from ...db.types import utc_now
from ...observability.credential_redaction import redact_credentials
from ...observability.logging_setup import get_logger
from .base import Frame, FrameSource, failed_frame
from .jpeg_utils import decode_jpeg

logger = get_logger(__name__)

# A real 640x480 JPEG from this camera is a few KB. Below 512 B it cannot be
# a real frame; above the cap it is either a misconfigured camera streaming
# something else or a hostile response - reject before decode either way so
# a faulty device cannot exhaust memory on the box.
MIN_BODY_BYTES = 512
MAX_BODY_BYTES = 2_000_000


class Esp32CamHttpSource(FrameSource):
    """One HTTP client per camera, reused across reads for connection keep-alive."""

    def __init__(self, camera_id: int, url: str, timeout_s: float) -> None:
        self._camera_id = camera_id
        self._url = url
        self._fail_streak = 0
        self._client = httpx.Client(timeout=httpx.Timeout(timeout_s))

    @property
    def camera_id(self) -> int:
        return self._camera_id

    @property
    def fail_streak(self) -> int:
        return self._fail_streak

    def read(self) -> Frame:
        try:
            response = self._client.get(self._url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return self._fail(f"{type(exc).__name__}: {exc}")

        body = response.content
        if not (MIN_BODY_BYTES <= len(body) <= MAX_BODY_BYTES):
            return self._fail(f"unexpected body size: {len(body)} bytes")

        image = decode_jpeg(body)
        if image is None:
            # Exactly the weak-WiFi truncation case the module docstring
            # warns about: a real failure, never a crash three layers up.
            return self._fail("undecodable JPEG (likely truncated on weak WiFi)")

        self._fail_streak = 0
        return Frame(
            camera_id=self._camera_id, timestamp=utc_now(), image=image, jpeg_bytes=body, ok=True
        )

    def close(self) -> None:
        self._client.close()

    def _fail(self, error: str) -> Frame:
        # Redacted at the origin, not at each sink. An httpx error stringifies
        # the request URL, so a camera configured with `user:password@host`
        # would otherwise write its own credentials into the log line, into
        # `cameras.last_error`, and from there into the camera list that every
        # security-role user can read.
        error = redact_credentials(error)
        self._fail_streak += 1
        logger.warning(
            "frame_read_failed",
            camera_id=self._camera_id,
            source="esp32cam_http",
            error=error,
            fail_streak=self._fail_streak,
        )
        return failed_frame(self._camera_id, error)
