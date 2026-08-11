"""Fan-out of camera frames to whoever is watching.

Two rules shape everything here.

Encode once. The JPEG published is the untouched bytes the camera sent; the
server never draws on a frame and never re-encodes one, because the overlay is
drawn client-side from the JSON header. On the target board, re-encoding per
viewer would cost real CPU for no visible benefit.

Never let a slow viewer slow anything down. Each subscriber owns a queue of
exactly one message and a task that drains it. A viewer that cannot keep up
loses frames - only its own - because a stale frame is worthless here: someone
watching a camera wants now, not a backlog.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict

from ..observability.logging_setup import get_logger

logger = get_logger(__name__)


class Subscriber:
    """One viewer of one camera."""

    __slots__ = ("_queue", "camera_id", "dropped")

    def __init__(self, camera_id: int) -> None:
        self.camera_id = camera_id
        # maxsize=1: hold the latest frame, never a backlog.
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)
        self.dropped = 0

    def offer(self, message: bytes) -> None:
        """Latest-wins. Never blocks, never awaits, never raises."""
        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            # Discard the frame this viewer has not collected yet and replace
            # it. Publishing must not await a socket - one slow client would
            # otherwise stall every other viewer and the camera loop itself.
            # Both suppressions cover the same race: the sender task draining
            # the queue between our checks. Either way the newest frame wins.
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
            self.dropped += 1
            with contextlib.suppress(asyncio.QueueFull):
                self._queue.put_nowait(message)

    async def get(self) -> bytes:
        return await self._queue.get()


class BroadcastHub:
    """Routes published frames to the subscribers of each camera."""

    def __init__(self) -> None:
        self._subscribers: dict[int, set[Subscriber]] = defaultdict(set)

    def viewer_count(self, camera_id: int) -> int:
        return len(self._subscribers[camera_id])

    def subscribe(self, camera_id: int) -> Subscriber:
        subscriber = Subscriber(camera_id)
        self._subscribers[camera_id].add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: Subscriber) -> None:
        self._subscribers[subscriber.camera_id].discard(subscriber)

    def publish(self, camera_id: int, message: bytes) -> int:
        """Hand the same bytes to every viewer. Returns how many were reached.

        Synchronous and non-blocking on purpose: the camera loop calls this on
        its hot path and must never wait on a socket.
        """
        subscribers = self._subscribers.get(camera_id)
        if not subscribers:
            return 0
        for subscriber in subscribers:
            subscriber.offer(message)
        return len(subscribers)

    def has_viewers(self, camera_id: int) -> bool:
        return bool(self._subscribers.get(camera_id))

    def close_all(self) -> None:
        total = sum(len(group) for group in self._subscribers.values())
        self._subscribers.clear()
        if total:
            logger.info("broadcast_hub_closed", subscribers=total)
