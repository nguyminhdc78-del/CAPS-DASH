"""Asking a running camera loop to pick up new configuration.

The subtle part: REST handlers are sync `def` functions running in FastAPI's
threadpool, while the camera loops are asyncio tasks on the event loop.
`asyncio.Event.set()` is not thread-safe, so a handler setting one directly is
a race that will work in testing and fail occasionally in production.

Everything here therefore goes through `loop.call_soon_threadsafe`.
"""

from __future__ import annotations

import asyncio


class ReloadSignals:
    """Cross-thread reload requests, one event per camera plus a global one."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._events: dict[int, asyncio.Event] = {}
        self._reconcile = asyncio.Event()

    def event_for(self, camera_id: int) -> asyncio.Event:
        return self._events.setdefault(camera_id, asyncio.Event())

    @property
    def reconcile_event(self) -> asyncio.Event:
        return self._reconcile

    def request(self, camera_id: int) -> None:
        """Reload one camera's slot map or tuning. Safe from any thread."""
        self._loop.call_soon_threadsafe(self.event_for(camera_id).set)

    def request_reconcile(self) -> None:
        """A camera was added, removed, enabled or disabled. Safe from any thread."""
        self._loop.call_soon_threadsafe(self._reconcile.set)

    def take(self, camera_id: int) -> bool:
        """Consume a pending request for this camera, if there is one."""
        event = self.event_for(camera_id)
        if event.is_set():
            event.clear()
            return True
        return False

    def take_reconcile(self) -> bool:
        if self._reconcile.is_set():
            self._reconcile.clear()
            return True
        return False

    def forget(self, camera_id: int) -> None:
        self._events.pop(camera_id, None)
