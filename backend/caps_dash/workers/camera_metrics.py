"""Per-camera counters, for the dashboard and for the offline alert."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from ..db.types import utc_now


@dataclass(slots=True)
class CameraMetrics:
    """What the operations page shows about one camera."""

    frames_ok: int = 0
    frames_failed: int = 0
    fail_streak: int = 0
    errors: int = 0
    last_process_ms: float = 0.0
    last_tick_ms: float = 0.0
    last_error: str = ""
    last_seen_at: dt.datetime | None = None
    # Rolling average so a single slow frame does not dominate the reading.
    average_process_ms: float = 0.0
    _samples: int = field(default=0, repr=False)

    def record_success(self, *, process_ms: float, tick_ms: float) -> None:
        self.frames_ok += 1
        self.fail_streak = 0
        self.last_process_ms = process_ms
        self.last_tick_ms = tick_ms
        self.last_seen_at = utc_now()
        self._samples += 1
        self.average_process_ms += (process_ms - self.average_process_ms) / self._samples

    def record_failure(self, error: str) -> None:
        self.frames_failed += 1
        self.fail_streak += 1
        self.last_error = error

    def record_error(self, error: str = "") -> None:
        """An unexpected exception, as distinct from a camera that did not answer."""
        self.errors += 1
        if error:
            self.last_error = error

    def is_online(self, offline_after: int) -> bool:
        """Never seen is not the same as offline, but both are 'not online'."""
        return self.frames_ok > 0 and self.fail_streak < offline_after
