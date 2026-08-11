"""Synthetic in-memory frame source - no camera, no file, no model.

Required infrastructure alongside `FakeVehicleDetector`: it is what lets a
demo or a CI run drive the full capture -> decode -> detect -> assign chain
with zero external dependencies.
"""

from __future__ import annotations

import numpy as np

from ...db.types import utc_now
from .base import Frame, FrameSource, failed_frame
from .jpeg_utils import encode_jpeg

# h, w - matches the ESP32-CAM's 640x480 delivery so downstream code sees a
# realistic frame size even when nothing real is attached.
DEFAULT_SIZE = (480, 640)


class FakeSource(FrameSource):
    """Generates a solid-colour frame that cycles through grey levels.

    `fail_next(n)` schedules the next `n` reads to fail, so tests can exercise
    `fail_streak` accounting and the never-raise contract without a real
    camera or file on disk.
    """

    def __init__(self, camera_id: int = 0, size: tuple[int, int] = DEFAULT_SIZE) -> None:
        self._camera_id = camera_id
        self._height, self._width = size
        self._frame_index = 0
        self._fail_streak = 0
        self._scheduled_failures = 0

    @property
    def camera_id(self) -> int:
        return self._camera_id

    @property
    def fail_streak(self) -> int:
        return self._fail_streak

    def fail_next(self, count: int) -> None:
        self._scheduled_failures += count

    def read(self) -> Frame:
        if self._scheduled_failures > 0:
            self._scheduled_failures -= 1
            self._fail_streak += 1
            return failed_frame(self._camera_id, "scheduled test failure")

        image = np.zeros((self._height, self._width, 3), dtype=np.uint8)
        level = self._frame_index % 256
        image[:] = (level, level, level)
        self._frame_index += 1

        jpeg_bytes = encode_jpeg(image)
        self._fail_streak = 0
        return Frame(
            camera_id=self._camera_id,
            timestamp=utc_now(),
            image=image,
            jpeg_bytes=jpeg_bytes,
            ok=True,
        )

    def close(self) -> None:
        pass
