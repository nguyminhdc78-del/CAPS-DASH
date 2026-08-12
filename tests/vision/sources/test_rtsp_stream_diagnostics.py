"""The lag tracker's arithmetic.

Time is injected through a fake `monotonic`, so a test can express "ten
seconds of wall clock passed while the stream advanced two seconds" without
actually waiting - which is the only situation the tracker exists to detect.
"""

from __future__ import annotations

import pytest

from caps_dash.vision.sources import rtsp_stream_diagnostics
from caps_dash.vision.sources.rtsp_stream_diagnostics import StreamLagTracker


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """A mutable one-element list holding the current fake time."""
    now = [0.0]
    monkeypatch.setattr(rtsp_stream_diagnostics.time, "monotonic", lambda: now[0])
    return now


def test_no_report_until_the_interval_is_reached(clock: list[float]) -> None:
    tracker = StreamLagTracker(every_s=1.0)

    assert tracker.note_frame(0.0) is None  # the first frame only sets the origin
    clock[0] += 0.4
    assert tracker.note_frame(400.0) is None
    clock[0] += 0.4
    assert tracker.note_frame(800.0) is None
    clock[0] += 0.4
    assert tracker.note_frame(1200.0) is not None


def test_a_reader_keeping_up_reports_no_lag(clock: list[float]) -> None:
    tracker = StreamLagTracker(every_s=0.5)
    tracker.note_frame(0.0)

    # Two frames a third of a second apart, and a third of a second of wall
    # clock to match: the reader is exactly keeping pace.
    clock[0] += 1 / 3
    tracker.note_frame(333.0)
    clock[0] += 1 / 3
    report = tracker.note_frame(666.0)

    assert report is not None
    assert report.lag_s == pytest.approx(0.0, abs=0.01)
    assert report.decode_fps == pytest.approx(3.0, abs=0.1)


def test_a_reader_falling_behind_reports_growing_lag(clock: list[float]) -> None:
    """The case that matters. Measured on the board: the stream advanced 1.8 s
    while 30.4 s of real time passed, so the picture was half a minute old and
    getting older."""
    tracker = StreamLagTracker(every_s=1.0)
    tracker.note_frame(0.0)

    clock[0] += 10.0
    first = tracker.note_frame(1000.0)  # stream advanced 1 s in 10 s of wall clock
    clock[0] += 10.0
    second = tracker.note_frame(2000.0)

    assert first is not None and second is not None
    assert first.lag_s == pytest.approx(9.0, abs=0.01)
    assert second.lag_s == pytest.approx(18.0, abs=0.01)
    # The growth figure is what separates "a fixed delay" from "losing ground".
    assert second.lag_growth_s == pytest.approx(9.0, abs=0.01)


def test_a_collapsed_decode_rate_is_still_checked_on_time(clock: list[float]) -> None:
    """The fault a frame-counted interval had.

    Reporting every N frames stretched the gap between checks in exact
    proportion to the failure it exists to catch: at 5 fps a 150-frame
    interval was 30 s and at 1 fps two and a half minutes, so the picture
    could be a minute stale before anything looked at it. On wall clock the
    check lands just as often however badly the link is behaving.
    """
    tracker = StreamLagTracker(every_s=1.0)
    tracker.note_frame(0.0)

    # One frame a second reaching the reader, while the camera sends thirty:
    # the stream advances 1/30 s per frame against 1 s of real time.
    reports = []
    for frame in range(1, 6):
        clock[0] += 1.0
        report = tracker.note_frame(frame * 1000.0 / 30.0)
        if report is not None:
            reports.append(report)

    assert len(reports) == 5  # one per second of wall clock, not one per 150 frames
    assert reports[-1].lag_s == pytest.approx(5.0 - 5.0 / 30.0, abs=0.01)


def test_a_fixed_delay_shows_no_growth(clock: list[float]) -> None:
    """A constant lag is a buffer somewhere and merely annoying; only growth
    means the reader is being outrun."""
    tracker = StreamLagTracker(every_s=1.0)
    tracker.note_frame(0.0)

    clock[0] += 5.0
    tracker.note_frame(1000.0)  # 4 s behind
    clock[0] += 1.0
    report = tracker.note_frame(2000.0)  # still 4 s behind

    assert report is not None
    assert report.lag_growth_s == pytest.approx(0.0, abs=0.01)


def test_reset_starts_a_new_timeline(clock: list[float]) -> None:
    """A reconnect must not report the outage itself as lag."""
    tracker = StreamLagTracker(every_s=1.0)
    tracker.note_frame(0.0)
    clock[0] += 60.0

    tracker.reset()
    assert tracker.note_frame(500_000.0) is None  # new origin, no report

    clock[0] += 1.0
    report = tracker.note_frame(501_000.0)

    assert report is not None
    assert report.lag_s == pytest.approx(0.0, abs=0.01)


@pytest.mark.parametrize("every_s", [0.0, -1.0])
def test_a_non_positive_interval_is_rejected(every_s: float) -> None:
    with pytest.raises(ValueError):
        StreamLagTracker(every_s=every_s)
