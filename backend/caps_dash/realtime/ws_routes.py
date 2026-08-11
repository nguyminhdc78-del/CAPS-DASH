"""The camera stream endpoint. Orchestration only.

Three concurrent jobs per connection - sending frames, reading control
messages, pinging - and whichever finishes first ends the connection. That is
`asyncio.wait(FIRST_COMPLETED)` rather than `gather`: with gather, a client
that hangs up mid-stream would leave the heartbeat pinging a dead socket
forever.
"""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..app_state import AppState
from ..db.models import Camera
from ..db.session import session_scope
from ..observability.logging_setup import get_logger
from . import close_codes
from .broadcast_hub import BroadcastHub
from .subscriber import Subscriber
from .ws_auth import authenticate_connection
from .ws_control import read_control_messages
from .ws_heartbeat import Heartbeat

logger = get_logger(__name__)

router = APIRouter()


@router.websocket("/cameras/{camera_id}")
async def camera_stream(websocket: WebSocket, camera_id: int) -> None:
    """Live frames for one camera. Security role or above."""
    state: AppState = websocket.app.state.caps
    session_factory = state.require_session_factory()
    hub: BroadcastHub = state.hub

    viewer = await authenticate_connection(websocket, state.settings, session_factory)
    if viewer is None:
        return  # already closed, with a reason

    if not await asyncio.to_thread(_camera_is_streamable, session_factory, camera_id):
        await _close(websocket, close_codes.POLICY_VIOLATION, close_codes.REASON_CAMERA_UNKNOWN)
        return

    settings = state.settings
    if (
        hub.viewer_count(camera_id) >= settings.ws_max_viewers_per_camera
        or hub.total_viewers() >= settings.ws_max_connections_total
    ):
        # On this hardware the honest failure is refusing one viewer, not
        # degrading the stream for everyone already watching.
        await _close(
            websocket, close_codes.TRY_AGAIN_LATER, close_codes.REASON_TOO_MANY_VIEWERS
        )
        return

    await websocket.send_json(
        {"type": "auth_ok", "camera_id": camera_id, "role": viewer.user.role}
    )

    log = logger.bind(camera_id=camera_id, username=viewer.user.username)
    subscriber = hub.subscribe(camera_id)
    heartbeat = Heartbeat(settings.ws_heartbeat_s, viewer.expires_at)
    reason = close_codes.REASON_SERVER_ERROR
    code = close_codes.INTERNAL_ERROR

    try:
        cached = hub.last_message(camera_id, settings.ws_first_frame_max_age_s)
        if cached is not None:
            # Show something at once. Waiting a full poll interval for the
            # first frame reads as a broken page.
            await websocket.send_bytes(cached)

        log.info("ws_stream_opened", viewers=hub.viewer_count(camera_id))
        reason, code = await _run_connection(websocket, subscriber, heartbeat)

    except WebSocketDisconnect:
        reason, code = "", close_codes.NORMAL
    except Exception:
        log.exception("ws_stream_failed")
    finally:
        hub.unsubscribe(subscriber)
        await subscriber.stop_sender()
        log.info(
            "ws_stream_closed",
            reason=reason or "client_disconnect",
            sent=subscriber.sent,
            dropped=subscriber.dropped,
        )
        if reason:
            await _close(websocket, code, reason)


async def _run_connection(
    websocket: WebSocket, subscriber: Subscriber, heartbeat: Heartbeat
) -> tuple[str, int]:
    """Run sender, receiver and heartbeat until the first one finishes."""
    sender = subscriber.start_sender(websocket)
    receiver = asyncio.create_task(read_control_messages(websocket, heartbeat))
    pinger = asyncio.create_task(heartbeat.run(websocket))

    running: set[asyncio.Task[None] | asyncio.Task[str]] = {sender, receiver, pinger}
    done, pending = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    # Only the heartbeat ends with something to say. The sender and the
    # receiver finish because the socket went away, which needs no close frame.
    if pinger in done and not pinger.cancelled():
        reason = pinger.result()
        # An expired token is a policy decision the client must react to by
        # refreshing and reconnecting; a lost heartbeat is just the connection
        # going away. Phase 12 branches on the difference.
        code = (
            close_codes.POLICY_VIOLATION
            if reason == close_codes.REASON_TOKEN_EXPIRED
            else close_codes.GOING_AWAY
        )
        return reason, code
    return "", close_codes.NORMAL


def _camera_is_streamable(session_factory: sessionmaker[Session], camera_id: int) -> bool:
    """A disabled camera has no worker, so its stream would never produce a frame."""
    with session_scope(session_factory) as session:
        return bool(
            session.execute(
                select(Camera.id).where(
                    Camera.id == camera_id, Camera.is_enabled.is_(True)
                )
            ).scalar_one_or_none()
        )


async def _close(websocket: WebSocket, code: int, reason: str) -> None:
    with contextlib.suppress(RuntimeError, WebSocketDisconnect):
        await websocket.close(code=code, reason=reason)
