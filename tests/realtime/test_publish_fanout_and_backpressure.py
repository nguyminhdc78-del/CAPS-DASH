"""Fan-out costs one reference per viewer, and a slow viewer only hurts itself."""

from __future__ import annotations

import asyncio

from caps_dash.realtime.broadcast_hub import BroadcastHub
from caps_dash.realtime.frame_protocol import decode_frame_message, encode_frame_message


async def test_publish_hands_every_subscriber_the_same_object():
    """The identity check is the test.

    If a future change re-encodes or copies per viewer, these stop being the
    same object and the CPU cost of a stream becomes proportional to the number
    of people watching - the one thing this design refuses to do.
    """
    hub = BroadcastHub()
    subscribers = [hub.subscribe(1) for _ in range(5)]
    message = encode_frame_message({"seq": 1}, b"\xff\xd8jpeg")

    assert hub.publish(1, message) == 5

    for subscriber in subscribers:
        assert await subscriber.get() is message


# Encode-once is asserted against the real camera loop, in
# `tests/workers/test_camera_loop_integration.py` - counting a helper this
# module calls itself would prove nothing about the code that actually encodes.


async def test_slow_viewer_drops_frames_and_never_blocks_publish():
    """Latest-wins: the queue holds one frame, and the newest one wins."""
    hub = BroadcastHub()
    slow = hub.subscribe(1)
    fast = hub.subscribe(1)

    received: list[bytes] = []
    for seq in range(50):
        hub.publish(1, encode_frame_message({"seq": seq}, b"x"))
        # The fast viewer collects every tick; the slow one never does.
        received.append(await fast.get())

    assert len(received) == 50
    assert slow.dropped == 49  # 50 offered, 1 still queued, the rest replaced

    # And the frame it still holds is the newest, not the oldest.
    assert decode_frame_message(await slow.get()).header["seq"] == 49


async def test_publishing_to_nobody_is_free_but_still_caches():
    """A viewer connecting later gets a picture immediately, not after a poll."""
    hub = BroadcastHub()
    message = encode_frame_message({"seq": 9}, b"jpeg")

    assert hub.publish(3, message) == 0
    assert hub.last_message(3, max_age_s=30.0) is message


async def test_a_stale_cached_frame_is_not_served_as_the_first_paint():
    """The loop only publishes while somebody watches.

    So the cache can hold the last frame before everyone left. Serving that
    hours later as the opening frame of a live view is worse than showing
    nothing - the viewer has no way to tell it is not current.
    """
    hub = BroadcastHub()
    hub.publish(5, encode_frame_message({"seq": 1}, b"jpeg"))
    await asyncio.sleep(0.02)

    assert hub.last_message(5, max_age_s=0.01) is None
    assert hub.last_message(5, max_age_s=30.0) is not None


async def test_forget_drops_a_deleted_cameras_still():
    """Camera ids are SQLite rowids, and rowids get reused.

    Without this, the next camera to take a deleted camera's id would greet
    its first viewer with the deleted camera's picture.
    """
    hub = BroadcastHub()
    hub.publish(4, encode_frame_message({"seq": 1}, b"jpeg"))
    hub.forget(4)
    assert hub.last_message(4, max_age_s=30.0) is None
