"""One viewer of one camera, and the task that feeds its socket.

The rule this file exists to enforce: **publishing never awaits a socket.**
A naive fan-out (`for client in clients: await client.send_bytes(...)`) makes
every viewer wait for the slowest one, and puts that wait on the camera loop's
hot path. Here each viewer owns a one-slot queue and a task that drains it, so
a client on a bad connection degrades its own frame rate and nobody else's.

The queue holds exactly one message on purpose. Someone watching a camera wants
*now*; a backlog of stale frames is worse than useless, because the viewer
would fall further behind with every tick and never catch up.
"""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import WebSocket


class Subscriber:
    """A single WebSocket viewer of a single camera."""

    __slots__ = ("_queue", "_task", "camera_id", "dropped", "sent")

    def __init__(self, camera_id: int) -> None:
        self.camera_id = camera_id
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)
        self._task: asyncio.Task[None] | None = None
        self.dropped = 0
        self.sent = 0

    def offer(self, message: bytes) -> None:
        """Latest-wins. Never blocks, never awaits, never raises."""
        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            # Discard the frame this viewer has not collected yet and replace
            # it with the newer one. Both suppressions cover the same race -
            # the sender task draining the queue between our two calls. Either
            # way the newest frame is the one that survives.
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
            self.dropped += 1
            with contextlib.suppress(asyncio.QueueFull):
                self._queue.put_nowait(message)

    async def get(self) -> bytes:
        return await self._queue.get()

    def start_sender(self, websocket: WebSocket) -> asyncio.Task[None]:
        """Spawn the task that forwards queued frames to this socket."""
        self._task = asyncio.create_task(
            self._send_forever(websocket), name=f"ws-sender-{self.camera_id}"
        )
        return self._task

    async def stop_sender(self) -> None:
        """Tear the sender down. Never raises.

        `_send_forever` deliberately lets exceptions escape so the endpoint
        notices a dead socket - which means that by the time we get here the
        task may already have finished with one, and awaiting it would re-raise
        into the endpoint's `finally`, skipping the close and the log line.
        Teardown is not where a socket error is handled.
        """
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    async def _send_forever(self, websocket: WebSocket) -> None:
        """Drain the queue into the socket until the connection goes away.

        Exceptions are deliberately not swallowed: the endpoint waits on this
        task and tears the connection down when it ends. Silently looping on a
        dead socket is how a server accumulates zombie tasks.
        """
        while True:
            message = await self.get()
            await websocket.send_bytes(message)
            self.sent += 1
