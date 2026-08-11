"""Cycles through JPEG stills in a directory.

Not test scaffolding: there is no camera hardware on hand, so this is one of
the sources dev, demo and CI genuinely run the whole pipeline against.
"""

from __future__ import annotations

from pathlib import Path

from ...db.types import utc_now
from ...observability.logging_setup import get_logger
from .base import Frame, FrameSource, failed_frame
from .jpeg_utils import decode_jpeg

logger = get_logger(__name__)


class ImageFolderSource(FrameSource):
    """Serves `*.jpg` / `*.jpeg` files from `directory`, sorted, looping forever."""

    def __init__(self, camera_id: int, directory: Path) -> None:
        self._camera_id = camera_id
        self._directory = directory
        self._paths = sorted({*directory.glob("*.jpg"), *directory.glob("*.jpeg")})
        self._index = 0
        self._fail_streak = 0
        self._last_served: Path | None = None

    @property
    def camera_id(self) -> int:
        return self._camera_id

    @property
    def fail_streak(self) -> int:
        return self._fail_streak

    def describe(self) -> str:
        """Which file was served last - useful when a test or demo behaves oddly."""
        return str(self._last_served) if self._last_served else "(nothing served yet)"

    def read(self) -> Frame:
        if not self._paths:
            self._fail_streak += 1
            return failed_frame(self._camera_id, f"no jpg files in {self._directory}")

        path = self._paths[self._index % len(self._paths)]
        self._index += 1
        self._last_served = path

        try:
            body = path.read_bytes()
        except OSError as exc:
            self._fail_streak += 1
            return failed_frame(self._camera_id, f"read failed for {path.name}: {exc}")

        image = decode_jpeg(body)
        if image is None:
            self._fail_streak += 1
            return failed_frame(self._camera_id, f"undecodable JPEG: {path.name}")

        self._fail_streak = 0
        return Frame(
            camera_id=self._camera_id, timestamp=utc_now(), image=image, jpeg_bytes=body, ok=True
        )

    def close(self) -> None:
        pass
