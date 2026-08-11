"""The client→server half of a stream connection.

Everything arriving here is treated as hostile: length-capped, parsed inside a
`try`, and unknown message types dropped without an echo. An endpoint that
reflects unrecognised input back is a free amplifier for whoever is probing it.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from ..observability.logging_setup import get_logger
from .ws_heartbeat import Heartbeat

logger = get_logger(__name__)

# Control messages are tiny. The cap is the point: a client must not be able to
# make the server allocate by sending one enormous frame.
MAX_CONTROL_MESSAGE_BYTES = 4096


async def read_control_messages(websocket: WebSocket, heartbeat: Heartbeat) -> None:
    """Read until the client disconnects. Returns; never closes the socket itself."""
    while True:
        try:
            raw = await websocket.receive_text()
        except (WebSocketDisconnect, RuntimeError, KeyError):
            # KeyError: Starlette raises it when a binary frame arrives on a
            # text receive. A client sending us bytes has nothing to say that
            # this protocol defines, so the connection ends.
            return

        message = _parse(raw)
        if message is None:
            continue

        kind = message.get("type")
        if kind == "ping":
            await websocket.send_json({"type": "pong"})
        elif kind == "pong":
            heartbeat.record_pong()
        elif kind == "set_confidence":
            # Refused on purpose. Tuning goes through PATCH
            # /api/cameras/{id}/runtime so it is authorised and audited - a
            # setting changed over an anonymous-looking socket leaves no record
            # of who changed it or when.
            logger.info("ws_control_refused", kind=kind)
        # Anything else is ignored in silence.


def _parse(raw: str) -> dict[str, Any] | None:
    if len(raw) > MAX_CONTROL_MESSAGE_BYTES:
        return None
    try:
        message = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return message if isinstance(message, dict) else None
