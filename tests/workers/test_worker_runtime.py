"""Camera worker runtime: state diffing, framing, fan-out, reload signalling."""

from __future__ import annotations

import asyncio

import pytest

from caps_dash.realtime.broadcast_hub import BroadcastHub
from caps_dash.realtime.frame_protocol import (
    HEADER_LENGTH_BYTES,
    MAX_HEADER_BYTES,
    decode_frame_message,
    encode_frame_message,
)
from caps_dash.vision.domain import SlotState
from caps_dash.workers.camera_metrics import CameraMetrics
from caps_dash.workers.reload_signals import ReloadSignals
from caps_dash.workers.state_tracker import StateTracker

# --- State tracking ----------------------------------------------------------


def test_only_changes_are_reported() -> None:
    """History is written on change only; a 100-slot site scanned every second
    would otherwise produce 8.6 million rows a day on flash storage."""
    tracker = StateTracker()

    first = tracker.diff({"A1": SlotState.OCCUPIED, "A2": SlotState.FREE})
    assert {change.slot_code for change in first} == {"A1", "A2"}

    assert tracker.diff({"A1": SlotState.OCCUPIED, "A2": SlotState.FREE}) == []


def test_a_change_carries_both_states() -> None:
    tracker = StateTracker()
    tracker.diff({"A1": SlotState.FREE})

    change = tracker.diff({"A1": SlotState.OCCUPIED})[0]
    assert change.previous is SlotState.FREE
    assert change.new is SlotState.OCCUPIED


def test_warmup_unknown_is_not_recorded_as_a_change() -> None:
    """Every slot reads UNKNOWN while the vote filter warms up. Recording that
    at each restart would fill the history with rows that mean nothing."""
    tracker = StateTracker()
    assert tracker.diff({"A1": SlotState.UNKNOWN, "A2": SlotState.UNKNOWN}) == []

    # But a slot that was known and becomes unknown IS a real transition.
    tracker.diff({"A1": SlotState.OCCUPIED})
    assert len(tracker.diff({"A1": SlotState.UNKNOWN})) == 1


def test_reset_forgets_everything() -> None:
    tracker = StateTracker()
    tracker.diff({"A1": SlotState.FREE})
    tracker.reset()
    assert len(tracker.diff({"A1": SlotState.FREE})) == 1


# --- Frame protocol ----------------------------------------------------------


def test_frame_message_round_trips() -> None:
    header = {"camera_id": 1, "slots": [{"code": "A1", "state": "FREE"}]}
    jpeg = b"\xff\xd8\xff\xe0 not really a jpeg \xff\xd9"

    decoded = decode_frame_message(encode_frame_message(header, jpeg))

    assert decoded.header == header
    assert decoded.jpeg == jpeg


def test_frame_and_state_travel_as_one_message() -> None:
    """The reason for the format. Two messages could be split by a drop under
    backpressure, leaving polygons drawn over a frame they do not describe."""
    message = encode_frame_message({"seq": 7}, b"jpegbytes")
    declared = int.from_bytes(message[:HEADER_LENGTH_BYTES], "big")

    assert len(message) == HEADER_LENGTH_BYTES + declared + len(b"jpegbytes")


def test_empty_jpeg_is_representable() -> None:
    assert decode_frame_message(encode_frame_message({"a": 1}, b"")).jpeg == b""


def test_oversized_header_is_refused_when_encoding() -> None:
    with pytest.raises(ValueError, match="header too large"):
        encode_frame_message({"junk": "x" * (MAX_HEADER_BYTES + 1)}, b"")


def test_a_lying_length_prefix_is_rejected() -> None:
    """Never trust the declared length: allocate nothing on its word alone."""
    forged = (10_000).to_bytes(HEADER_LENGTH_BYTES, "big") + b'{"a":1}'
    with pytest.raises(ValueError, match="runs past the end"):
        decode_frame_message(forged)


def test_an_absurd_length_prefix_is_rejected_before_allocating() -> None:
    forged = (2**31).to_bytes(HEADER_LENGTH_BYTES, "big") + b"{}"
    with pytest.raises(ValueError, match="exceeds the limit"):
        decode_frame_message(forged)


def test_a_truncated_message_is_rejected() -> None:
    with pytest.raises(ValueError, match="shorter than its length prefix"):
        decode_frame_message(b"\x00\x01")


# --- Broadcast fan-out -------------------------------------------------------


async def test_every_viewer_receives_the_same_bytes() -> None:
    """Encoded once per tick, shared by reference - never re-encoded per client."""
    hub = BroadcastHub()
    first, second = hub.subscribe(1), hub.subscribe(1)

    message = encode_frame_message({"seq": 1}, b"frame")
    assert hub.publish(1, message) == 2

    assert await first.get() is message
    assert await second.get() is message


async def test_publishing_to_a_camera_nobody_watches_is_free() -> None:
    assert BroadcastHub().publish(99, b"anything") == 0


async def test_a_slow_viewer_only_loses_its_own_frames() -> None:
    """Latest-wins. A stale frame is worthless: a viewer wants now, not a
    backlog, and one slow client must not stall the camera loop."""
    hub = BroadcastHub()
    slow = hub.subscribe(1)
    fast = hub.subscribe(1)

    for index in range(5):
        hub.publish(1, encode_frame_message({"seq": index}, b"f"))
        if index < 4:
            await fast.get()  # the fast viewer keeps up

    # The slow one skipped straight to the newest frame.
    assert decode_frame_message(await slow.get()).header["seq"] == 4
    assert slow.dropped == 4
    # And the fast viewer was never held back.
    assert decode_frame_message(await fast.get()).header["seq"] == 4


async def test_publishing_never_blocks() -> None:
    hub = BroadcastHub()
    hub.subscribe(1)
    # No viewer is draining, yet a hundred publishes must all return promptly.
    for index in range(100):
        hub.publish(1, encode_frame_message({"seq": index}, b"f"))


async def test_unsubscribing_stops_delivery() -> None:
    hub = BroadcastHub()
    viewer = hub.subscribe(1)
    hub.unsubscribe(viewer)
    assert hub.publish(1, b"x") == 0
    assert not hub.has_viewers(1)


async def test_viewer_count_is_reported_per_camera() -> None:
    hub = BroadcastHub()
    hub.subscribe(1)
    hub.subscribe(1)
    hub.subscribe(2)
    assert hub.viewer_count(1) == 2
    assert hub.viewer_count(2) == 1


# --- Reload signalling -------------------------------------------------------


async def test_a_reload_request_is_consumed_once() -> None:
    signals = ReloadSignals(asyncio.get_running_loop())

    signals.request(7)
    await asyncio.sleep(0)  # let call_soon_threadsafe run

    assert signals.take(7) is True
    assert signals.take(7) is False


async def test_reload_requests_are_per_camera() -> None:
    signals = ReloadSignals(asyncio.get_running_loop())
    signals.request(1)
    await asyncio.sleep(0)

    assert signals.take(1) is True
    assert signals.take(2) is False


async def test_a_reconcile_request_is_separate_from_a_reload() -> None:
    signals = ReloadSignals(asyncio.get_running_loop())
    signals.request_reconcile()
    await asyncio.sleep(0)

    assert signals.take(1) is False
    assert signals.take_reconcile() is True
    assert signals.take_reconcile() is False


async def test_requests_can_be_made_from_another_thread() -> None:
    """REST handlers are sync and run in a threadpool; asyncio.Event.set is not
    thread-safe, so every request goes through call_soon_threadsafe."""
    signals = ReloadSignals(asyncio.get_running_loop())

    await asyncio.to_thread(signals.request, 3)
    await asyncio.sleep(0)

    assert signals.take(3) is True


# --- Metrics -----------------------------------------------------------------


def test_a_success_clears_the_failure_streak() -> None:
    metrics = CameraMetrics()
    metrics.record_failure("timeout")
    metrics.record_failure("timeout")
    assert metrics.fail_streak == 2

    metrics.record_success(process_ms=40.0, tick_ms=100.0)
    assert metrics.fail_streak == 0
    assert metrics.frames_ok == 1


def test_a_camera_is_offline_after_the_configured_streak() -> None:
    metrics = CameraMetrics()
    metrics.record_success(process_ms=1.0, tick_ms=1.0)
    for _ in range(3):
        metrics.record_failure("no answer")
    assert not metrics.is_online(offline_after=3)


def test_a_camera_never_seen_is_not_online() -> None:
    assert not CameraMetrics().is_online(offline_after=3)


def test_average_process_time_smooths_a_single_slow_frame() -> None:
    metrics = CameraMetrics()
    metrics.record_success(process_ms=40.0, tick_ms=100.0)
    metrics.record_success(process_ms=60.0, tick_ms=100.0)
    assert metrics.average_process_ms == pytest.approx(50.0)

