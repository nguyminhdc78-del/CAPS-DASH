"""Periodic job: alert on slots occupied longer than `settings.overstay_hours`.

Registered on the scheduler every 5 minutes. Deduplicated through
`alert_service.create_deduplicated` - a slot stuck occupied for a week
produces one alert, not one per tick.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..config.settings import Settings
from ..db.enums import AlertSeverity, AlertType, SlotState
from ..db.models import ParkingSlot
from ..db.session import session_scope
from ..db.types import utc_now
from ..observability.logging_setup import get_logger
from ..repositories import history_repository
from ..services import alert_rules, alert_service

logger = get_logger(__name__)


def run(factory: sessionmaker[Session], settings: Settings) -> None:
    now = utc_now()
    cutoff = alert_rules.overstay_cutoff(settings, now=now)

    with session_scope(factory) as session:
        overstaying = session.execute(
            select(ParkingSlot).where(
                ParkingSlot.current_state == SlotState.OCCUPIED,
                ParkingSlot.state_since.is_not(None),
                ParkingSlot.state_since < cutoff,
                ParkingSlot.is_active.is_(True),
            )
        ).scalars().all()

        for slot in overstaying:
            _alert_one(session, slot, settings=settings, now=now)


def _alert_one(
    session: Session, slot: ParkingSlot, *, settings: Settings, now: dt.datetime
) -> None:
    started = slot.state_since
    if started is None:
        return  # guarded by the caller's WHERE clause; satisfies mypy's Optional check

    latest = history_repository.latest_for_slot(session, slot.id)
    if latest is not None and latest.clock_suspect:
        # The row that set this occupancy was written under a suspect clock
        # (see `db/clock_guard.py`) - the duration derived from it cannot be
        # trusted, so do not alert on it.
        return

    hours = (now - started).total_seconds() / 3600
    alert_service.create_deduplicated(
        session,
        alert_type=AlertType.OVERSTAY,
        entity_type="slot",
        entity_id=str(slot.id),
        severity=AlertSeverity.WARNING,
        message_code="alert.overstay",
        message=f"Slot {slot.code} ({slot.floor}) has been occupied for {hours:.1f}h",
        details={"slot_code": slot.code, "floor": slot.floor, "hours": round(hours, 1)},
        settings=settings,
        now=now,
    )
