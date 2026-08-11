"""Persisting slot state changes.

Runs in the single-threaded database executor. SQLite allows exactly one
writer, so funnelling every write through one thread makes contention
structurally impossible rather than something `busy_timeout` has to absorb.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import Camera, ParkingSlot, SlotStateHistory
from ..db.session import session_scope
from ..db.types import utc_now
from ..observability.logging_setup import get_logger
from ..workers.state_tracker import SlotChange

logger = get_logger(__name__)


def persist_state_changes(
    factory: sessionmaker[Session], camera_id: int, changes: list[SlotChange]
) -> None:
    """Write one history row per changed slot and update the current state.

    Called from the database executor thread, so it opens its own session -
    a Session is not safe to share across threads.
    """
    if not changes:
        return

    with session_scope(factory) as session:
        camera = session.get(Camera, camera_id)
        if camera is None:
            # The camera was deleted between the tick starting and this write.
            # Nothing to attach the history to; drop it rather than crash the
            # writer thread and stall every other camera behind it.
            logger.warning("state_write_skipped", camera_id=camera_id, reason="camera gone")
            return

        slots = {
            slot.code: slot
            for slot in session.execute(
                select(ParkingSlot).where(ParkingSlot.camera_id == camera_id)
            ).scalars()
        }

        now = utc_now()
        for change in changes:
            slot = slots.get(change.slot_code)
            if slot is None:
                continue
            slot.current_state = change.new
            slot.state_since = now
            session.add(
                SlotStateHistory(
                    slot_id=slot.id,
                    camera_code=camera.code,
                    slot_code=slot.code,
                    floor=slot.floor,
                    previous_state=change.previous,
                    new_state=change.new,
                    changed_at=now,
                )
            )


def record_camera_seen(
    factory: sessionmaker[Session], camera_id: int, frame_width: int, frame_height: int
) -> None:
    """Positional wrapper for the executor.

    `loop.run_in_executor` cannot pass keyword arguments, and threading a
    functools.partial through the hot path reads worse than naming the two
    cases explicitly.
    """
    touch_camera_health(
        factory, camera_id, frame_width=frame_width, frame_height=frame_height, seen=True
    )


def record_camera_error(
    factory: sessionmaker[Session], camera_id: int, error: str
) -> None:
    """Positional wrapper for the executor. See `record_camera_seen`."""
    touch_camera_health(factory, camera_id, last_error=error, seen=False)


def touch_camera_health(
    factory: sessionmaker[Session],
    camera_id: int,
    *,
    frame_width: int = 0,
    frame_height: int = 0,
    last_error: str = "",
    seen: bool = True,
) -> None:
    """Record that a camera answered (or did not).

    Kept separate from the state writes and called far less often: this is
    status, not history, and writing it every tick would defeat the point of
    only persisting changes.
    """
    with session_scope(factory) as session:
        camera = session.get(Camera, camera_id)
        if camera is None:
            return
        if seen:
            camera.last_seen_at = utc_now()
            camera.last_error = ""
            if frame_width and frame_height:
                camera.frame_width = frame_width
                camera.frame_height = frame_height
        elif last_error:
            camera.last_error = last_error[:500]
