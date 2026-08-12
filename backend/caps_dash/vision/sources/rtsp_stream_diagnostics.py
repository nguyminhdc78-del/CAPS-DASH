"""Measuring how far behind real time an RTSP stream is running.

Split out of `rtsp_stream_source.py` to keep that module focused on pulling
frames, and because this is the piece worth testing on its own: the arithmetic
is what turns "the picture looks late" into a number somebody can act on.

The measurement compares each frame's own presentation timestamp against the
wall clock. Both are measured as elapsed time since the first frame of the
connection, so the camera's clock never has to agree with the board's - only
the RATES have to, and any drift between them is exactly the lag.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LagReport:
    """One checkpoint's view of whether the reader is keeping up."""

    frames: int
    """Frames decoded since the previous checkpoint."""
    decode_fps: float
    """Rate those frames were decoded at."""
    lag_s: float
    """How far behind real time the newest frame is."""
    lag_growth_s: float
    """Change in `lag_s` since the previous checkpoint.

    This is the number that matters. A constant lag is a fixed delay somewhere
    - the camera's encoder, a buffer - and is merely annoying. A GROWING lag
    means frames are arriving faster than they are being taken, and the view
    drifts further from reality for as long as the process runs.
    """


class StreamLagTracker:
    """Accumulates frame timestamps and reports every `every_s` of wall clock.

    **Timed, not frame-counted.** Reporting every N frames stretched the gap
    between checks in exact proportion to the fault it exists to catch: the
    reader falls behind because frames are arriving slower than they are sent,
    so at 5 fps a 150-frame interval is 30 s, and at 1 fps it is two and a
    half minutes. The picture could be a minute stale before anything looked.
    A wall-clock interval checks just as often however badly the link is
    behaving - which is when it matters.
    """

    __slots__ = (
        "_every_s",
        "_first_pts_ms",
        "_first_wall",
        "_last_lag_s",
        "_since_report",
        "_since_report_wall",
    )

    def __init__(self, every_s: float = 1.0) -> None:
        if every_s <= 0:
            raise ValueError("report interval must be a positive number of seconds")
        self._every_s = every_s
        self._first_pts_ms: float | None = None
        self._first_wall = 0.0
        self._since_report = 0
        self._since_report_wall = 0.0
        self._last_lag_s: float | None = None

    def reset(self) -> None:
        """Forget everything. Called on reconnect: a new connection starts a
        new timeline, and comparing across the gap would report the outage as
        lag."""
        self._first_pts_ms = None
        self._last_lag_s = None
        self._since_report = 0

    def note_frame(self, pts_ms: float) -> LagReport | None:
        """Record one decoded frame. Returns a report every `every_s`."""
        now = time.monotonic()

        if self._first_pts_ms is None:
            self._first_pts_ms = pts_ms
            self._first_wall = now
            self._since_report_wall = now
            self._since_report = 0
            return None

        self._since_report += 1
        if now - self._since_report_wall < self._every_s:
            return None

        wall_elapsed = now - self._first_wall
        stream_elapsed = (pts_ms - self._first_pts_ms) / 1000.0
        lag_s = wall_elapsed - stream_elapsed

        window = now - self._since_report_wall
        decode_fps = self._since_report / window if window > 0 else 0.0
        growth = 0.0 if self._last_lag_s is None else lag_s - self._last_lag_s

        report = LagReport(
            frames=self._since_report,
            decode_fps=decode_fps,
            lag_s=lag_s,
            lag_growth_s=growth,
        )
        self._last_lag_s = lag_s
        self._since_report = 0
        self._since_report_wall = now
        return report
