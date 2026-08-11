"""Fan-out of camera frames to whoever is watching.

Two rules shape everything here.

Encode once. The JPEG published is the untouched bytes the camera sent; the
server never draws on a frame and never re-encodes one, because the overlay is
drawn client-side from the JSON header. On the target board, re-encoding per
viewer would cost real CPU for no visible benefit. Fan-out is therefore a
reference copy per subscriber, whatever the frame size.

Never let a slow viewer slow anything down. That rule lives in `Subscriber`.
"""

from __future__ import annotations

import time
from collections import defaultdict

from ..observability.logging_setup import get_logger
from .subscriber import Subscriber

logger = get_logger(__name__)


class BroadcastHub:
    """Routes published frames to the subscribers of each camera."""

    def __init__(self) -> None:
        self._subscribers: dict[int, set[Subscriber]] = defaultdict(set)
        # The most recent message per camera, so a client that has just
        # connected sees a picture immediately instead of staring at an empty
        # box for up to a poll interval - three seconds by default, which
        # reads as a broken page. Stamped, because the camera loop only
        # publishes while somebody is watching: without an age check the last
        # frame before everyone left would be served hours later as if it were
        # live, which is worse than showing nothing.
        self._last_message: dict[int, tuple[float, bytes]] = {}

    def viewer_count(self, camera_id: int) -> int:
        return len(self._subscribers[camera_id])

    def total_viewers(self) -> int:
        return sum(len(group) for group in self._subscribers.values())

    def subscribe(self, camera_id: int) -> Subscriber:
        subscriber = Subscriber(camera_id)
        self._subscribers[camera_id].add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: Subscriber) -> None:
        self._subscribers[subscriber.camera_id].discard(subscriber)

    def last_message(self, camera_id: int, max_age_s: float) -> bytes | None:
        """The cached still, or None once it is too old to pass for live."""
        stamped = self._last_message.get(camera_id)
        if stamped is None:
            return None
        published_at, message = stamped
        if time.monotonic() - published_at > max_age_s:
            return None
        return message

    def publish(self, camera_id: int, message: bytes) -> int:
        """Hand the same bytes to every viewer. Returns how many were reached.

        Synchronous and non-blocking on purpose: the camera loop calls this on
        its hot path and must never wait on a socket. The subscriber set is
        snapshotted before iterating, because a viewer disconnecting on the
        event loop mid-publish would otherwise mutate the set being walked.
        """
        self._last_message[camera_id] = (time.monotonic(), message)
        subscribers = self._subscribers.get(camera_id)
        if not subscribers:
            return 0
        for subscriber in tuple(subscribers):
            subscriber.offer(message)
        return len(subscribers)

    def has_viewers(self, camera_id: int) -> bool:
        return bool(self._subscribers.get(camera_id))

    def forget(self, camera_id: int) -> None:
        """Drop a deleted camera's cached still so it cannot outlive the camera."""
        self._last_message.pop(camera_id, None)
        self._subscribers.pop(camera_id, None)

    def close_all(self) -> None:
        total = self.total_viewers()
        self._subscribers.clear()
        self._last_message.clear()
        if total:
            logger.info("broadcast_hub_closed", subscribers=total)
