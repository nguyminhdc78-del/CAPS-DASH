"""Application-level heartbeat, and the mid-stream token check that rides on it.

Two things a TCP connection cannot tell us: whether the browser tab is still
alive behind a NAT that has quietly dropped state, and whether the credential
that opened the stream is still valid twenty minutes later. Both are answered
here.

Deliberately slower than uvicorn's protocol-level ping. Two independent pings
at similar intervals produce confusing traffic and double the wakeups on a
board where wakeups cost something.
"""

from __future__ import annotations

import asyncio
import datetime as dt

from fastapi import WebSocket

from . import close_codes

# Missing this many consecutive pings ends the connection. Two rather than one
# so a single dropped packet on hotel wifi does not kill a working stream.
MAX_MISSED_PINGS = 2


class Heartbeat:
    """Pings the client on a timer and gives up when it stops answering."""

    __slots__ = ("_interval_s", "_missed", "expires_at")

    def __init__(self, interval_s: float, expires_at: dt.datetime | None) -> None:
        self._interval_s = interval_s
        self._missed = 0
        self.expires_at = expires_at

    def record_pong(self) -> None:
        self._missed = 0

    @property
    def token_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return dt.datetime.now(dt.UTC) >= self.expires_at

    async def run(self, websocket: WebSocket) -> str:
        """Ping until the client stops answering or its token runs out.

        Returns the close reason. Returning rather than closing keeps the
        socket owned by exactly one place - the endpoint's `finally`.
        """
        while True:
            await asyncio.sleep(self._interval_s)

            if self.token_expired:
                # The stream outlived the credential that opened it. The client
                # refreshes and reconnects; letting it run on would leave an
                # authenticated stream nobody re-authorised.
                return close_codes.REASON_TOKEN_EXPIRED

            if self._missed >= MAX_MISSED_PINGS:
                return close_codes.REASON_HEARTBEAT_LOST

            self._missed += 1
            await websocket.send_json({"type": "ping"})
