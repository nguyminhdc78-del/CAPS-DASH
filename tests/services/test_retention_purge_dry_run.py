"""`retention_service.purge`: dry-run reports counts and deletes nothing; a
real purge deletes only rows older than the cutoff, never touches an
unacknowledged alert, and never touches `audit_logs`.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from caps_dash.config.settings import Settings
from caps_dash.db.enums import AlertSeverity, AlertType, AuditAction, CameraSourceType, SlotState
from caps_dash.db.models import Alert, AuditLog, Camera, ParkingSlot, SlotStateHistory
from caps_dash.services import retention_service

NOW = dt.datetime(2026, 8, 11, 12, 0, 0, tzinfo=dt.UTC)
OLD = NOW - dt.timedelta(days=400)  # well past the default 6-month retention
RECENT = NOW - dt.timedelta(days=10)  # well within it


def _seed(db_session: Session) -> ParkingSlot:
    camera = Camera(code="CAM-A", name="Deck A", floor="B1", source_type=CameraSourceType.FAKE)
    slot = ParkingSlot(code="A1", floor="B1")
    camera.slots = [slot]
    db_session.add(camera)
    db_session.commit()

    db_session.add_all(
        [
            SlotStateHistory(
                slot_id=slot.id, camera_code="CAM-A", slot_code="A1", floor="B1",
                previous_state=SlotState.FREE, new_state=SlotState.OCCUPIED, changed_at=OLD,
            ),
            SlotStateHistory(
                slot_id=slot.id, camera_code="CAM-A", slot_code="A1", floor="B1",
                previous_state=SlotState.OCCUPIED, new_state=SlotState.FREE, changed_at=RECENT,
            ),
            Alert(
                alert_type=AlertType.OVERSTAY, severity=AlertSeverity.WARNING,
                message_code="alert.overstay", message="old, acknowledged",
                created_at=OLD, acknowledged_at=OLD + dt.timedelta(hours=1),
            ),
            Alert(
                alert_type=AlertType.OVERSTAY, severity=AlertSeverity.WARNING,
                message_code="alert.overstay", message="old, still open",
                created_at=OLD,  # unacknowledged - must survive regardless of age
            ),
            Alert(
                alert_type=AlertType.DISK_LOW, severity=AlertSeverity.WARNING,
                message_code="alert.disk_low", message="recent, acknowledged",
                created_at=RECENT, acknowledged_at=RECENT,
            ),
        ]
    )
    db_session.commit()
    return slot


def _counts(db_session: Session) -> tuple[int, int, int]:
    history = db_session.execute(select(func.count()).select_from(SlotStateHistory)).scalar_one()
    alerts = db_session.execute(select(func.count()).select_from(Alert)).scalar_one()
    audit = db_session.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    return int(history), int(alerts), int(audit)


def test_dry_run_reports_counts_and_deletes_nothing(
    db_session: Session, settings: Settings
) -> None:
    _seed(db_session)
    before = _counts(db_session)

    result = retention_service.purge(
        db_session, settings=settings, older_than_months=6, dry_run=True,
        actor_username="tester", now=NOW,
    )

    assert result.deleted_history_rows == 1  # only the OLD row would qualify
    assert result.deleted_alert_rows == 1  # only the old, acknowledged alert

    after = _counts(db_session)
    # Nothing gone except the audit row the dry run itself writes.
    assert after == (before[0], before[1], before[2] + 1)


def test_real_purge_deletes_only_old_history_and_acknowledged_alerts(
    db_session: Session, settings: Settings
) -> None:
    slot = _seed(db_session)

    result = retention_service.purge(
        db_session, settings=settings, older_than_months=6, dry_run=False,
        actor_username="tester", now=NOW,
    )

    assert result.deleted_history_rows == 1
    assert result.deleted_alert_rows == 1

    remaining_history = db_session.execute(
        select(SlotStateHistory).where(SlotStateHistory.slot_id == slot.id)
    ).scalars().all()
    assert [row.changed_at for row in remaining_history] == [RECENT]

    remaining_alert_messages = {
        row.message for row in db_session.execute(select(Alert)).scalars().all()
    }
    assert remaining_alert_messages == {"old, still open", "recent, acknowledged"}


def test_audit_logs_are_never_purged(db_session: Session, settings: Settings) -> None:
    _seed(db_session)
    db_session.add(AuditLog(username="boss", action=AuditAction.USER_UPDATED, created_at=OLD))
    db_session.commit()
    audit_before = db_session.execute(select(func.count()).select_from(AuditLog)).scalar_one()

    retention_service.purge(
        db_session, settings=settings, older_than_months=6, dry_run=False,
        actor_username="tester", now=NOW,
    )

    audit_after = db_session.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    # Grew by exactly one (the purge's own audit row); the old row survives.
    assert audit_after == audit_before + 1


def test_purge_writes_an_audited_data_purged_row(db_session: Session, settings: Settings) -> None:
    _seed(db_session)

    retention_service.purge(
        db_session, settings=settings, older_than_months=6, dry_run=True,
        actor_username="tester", now=NOW,
    )

    audit_row = db_session.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.DATA_PURGED)
    ).scalar_one()
    assert audit_row.username == "tester"
    assert audit_row.after_json is not None
    assert audit_row.after_json["dry_run"] is True
