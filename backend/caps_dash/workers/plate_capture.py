"""Reading a plate at the one moment it is worth reading: a bay just filled.

Split from `inference_outcome_applier` because it answers a different question.
That module asks "what does this detection mean for slot state"; this one asks
"a car has arrived - which car?".

THE COST, AND WHY IT IS PAID HERE AND NOWHERE ELSE. A plate read costs about
1 s on the board, against a 3 s tick that already spends 1.5 s detecting
vehicles. Per tick it would not fit. Per arrival it is invisible: a bay fills
a few times a day, and between arrivals this module does nothing at all.

It runs in the SAME inference pool as the detector rather than a second one.
That serialises it behind vehicle detection - one tick's detection for one
camera is delayed when a car parks - which is the cheaper of the two prices.
A second pool would mean a second model resident in RAM on a board that has
975 MB free, and `inference_pool_size = 1` is a correctness constraint about
exactly that.
"""

from __future__ import annotations

import numpy as np
from structlog.stdlib import BoundLogger

from ..vision.domain import SlotMap, SlotState
from ..vision.plate_reader import looks_like_plate, read_plate
from .camera_context import CameraContext
from .state_tracker import SlotChange

# The detector's own confidence in "this rectangle is a plate". Separate from
# the vehicle detector's threshold, which is about "this is a car", and set
# low on purpose: a doubtful read is stored WITH its confidence so a guard can
# weigh it, whereas a discarded one leaves them with nothing to weigh.
MIN_PLATE_CONFIDENCE = 0.30


async def read_plates_for_filled_slots(
    context: CameraContext,
    changes: list[SlotChange],
    image: np.ndarray,
    fitted: SlotMap,
    log: BoundLogger,
) -> None:
    """Read a plate for every slot that has just become occupied.

    Only arrivals. A slot going FREE has nothing to photograph, and a slot
    that stayed OCCUPIED is the same car it was a tick ago - re-reading it
    would spend a second of the board's time to learn what is already known.
    """
    if not context.settings.plate_reading_enabled:
        return

    arrived = [change.slot_code for change in changes if change.new is SlotState.OCCUPIED]
    if not arrived:
        return

    polygons = {slot.id: slot.polygon for slot in fitted.slots}

    for code in arrived:
        polygon = polygons.get(code)
        if polygon is None:
            # The slot map was redrawn between the detection and this write.
            continue

        # In the inference pool, not on the event loop: this blocks for about
        # a second and the loop is serving every other camera and the API.
        read = await context.loop.run_in_executor(
            context.inference_pool, read_plate, image, polygon, MIN_PLATE_CONFIDENCE
        )

        if read is None:
            # The ordinary outcome for a car parked nose-in, a bay at a bad
            # angle, or a camera that cannot resolve the characters. Debug,
            # not warning: a car park where half the plates are unreadable
            # still counts its slots correctly, and a warning per arrival
            # would train everyone to ignore the log.
            log.debug("plate_not_read", slot=code)
            continue

        if not looks_like_plate(read.plate):
            log.debug("plate_rejected", slot=code, text=read.plate, reason="implausible")
            continue

        await context.loop.run_in_executor(
            context.db_pool,
            record_plate_read,
            context.session_factory,
            context.camera_id,
            code,
            read.plate,
            read.confidence,
            read.width_px,
        )
        log.info(
            "plate_read",
            slot=code,
            plate=read.plate,
            confidence=round(read.confidence, 2),
            width_px=read.width_px,
            process_ms=round(read.process_ms),
        )


def record_plate_read(
    factory: object,
    camera_id: int,
    slot_code: str,
    plate: str,
    confidence: float,
    width_px: int,
) -> None:
    """Write one read. Runs in the database executor, so it opens its own session."""
    # Imported here to keep the module importable in tests that never touch a
    # database, matching how the rest of the worker layer is arranged.
    from sqlalchemy import select

    from ..db.models import ParkingSlot, PlateRead
    from ..db.session import session_scope

    with session_scope(factory) as session:  # type: ignore[arg-type]
        slot_id = session.execute(
            select(ParkingSlot.id).where(
                ParkingSlot.camera_id == camera_id, ParkingSlot.code == slot_code
            )
        ).scalar_one_or_none()
        if slot_id is None:
            # The slot was deleted between the read and the write. Dropping the
            # row beats crashing the single writer thread that every camera's
            # state changes queue behind.
            return
        session.add(
            PlateRead(
                slot_id=slot_id,
                camera_id=camera_id,
                plate=plate,
                confidence=confidence,
                plate_width_px=width_px,
            )
        )
