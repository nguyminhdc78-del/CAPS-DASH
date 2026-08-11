"""`/alerts`: listing, filters, acknowledge (idempotent), audit trail, RBAC."""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from caps_dash.db.enums import AlertSeverity, AlertType, AuditAction
from caps_dash.db.models import Alert, AuditLog, User
from tests.api.conftest import auth_headers


def _seed_alerts(db: Session) -> dict[str, Alert]:
    now = dt.datetime.now(dt.UTC)
    open_critical = Alert(
        alert_type=AlertType.CAMERA_OFFLINE,
        severity=AlertSeverity.CRITICAL,
        message_code="alert.camera_offline",
        message="Camera CAM-1 stopped responding",
        created_at=now - dt.timedelta(minutes=5),
    )
    open_warning = Alert(
        alert_type=AlertType.OVERSTAY,
        severity=AlertSeverity.WARNING,
        message_code="alert.overstay",
        message="Slot A1 overstayed",
        created_at=now - dt.timedelta(hours=2),
    )
    acked = Alert(
        alert_type=AlertType.DISK_LOW,
        severity=AlertSeverity.INFO,
        message_code="alert.disk_low",
        message="Disk space low",
        created_at=now - dt.timedelta(days=1),
        acknowledged_at=now - dt.timedelta(hours=12),
    )
    db.add_all([open_critical, open_warning, acked])
    db.commit()
    return {"open_critical": open_critical, "open_warning": open_warning, "acked": acked}


def test_list_alerts_open_first_then_newest_first(
    client: TestClient, db: Session, guard: User
) -> None:
    _seed_alerts(db)
    response = client.get("/api/alerts", headers=auth_headers(client, "guard"))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    # Both open alerts (newest open first), then the acknowledged one.
    assert [item["alert_type"] for item in body["items"]] == [
        AlertType.CAMERA_OFFLINE.value,
        AlertType.OVERSTAY.value,
        AlertType.DISK_LOW.value,
    ]


def test_filter_by_acknowledged(client: TestClient, db: Session, guard: User) -> None:
    seeded = _seed_alerts(db)
    response = client.get(
        "/api/alerts", params={"acknowledged": "true"}, headers=auth_headers(client, "guard")
    )

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == seeded["acked"].id


def test_filter_by_type_and_severity(client: TestClient, db: Session, guard: User) -> None:
    seeded = _seed_alerts(db)
    response = client.get(
        "/api/alerts",
        params={"type": AlertType.OVERSTAY.value, "severity": AlertSeverity.WARNING.value},
        headers=auth_headers(client, "guard"),
    )

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == seeded["open_warning"].id


def test_acknowledge_sets_user_timestamp_and_writes_audit_row(
    client: TestClient, db: Session, guard: User
) -> None:
    seeded = _seed_alerts(db)
    alert_id = seeded["open_critical"].id

    response = client.post(
        f"/api/alerts/{alert_id}/acknowledge", headers=auth_headers(client, "guard")
    )

    assert response.status_code == 200
    body = response.json()
    assert body["acknowledged_by_id"] == guard.id
    assert body["acknowledged_at"] is not None

    audit_row = db.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.ALERT_ACKNOWLEDGED)
    ).scalar_one()
    assert audit_row.entity_id == str(alert_id)
    assert audit_row.username == "guard"


def test_double_acknowledge_is_idempotent(
    client: TestClient, db: Session, guard: User
) -> None:
    seeded = _seed_alerts(db)
    alert_id = seeded["open_warning"].id
    headers = auth_headers(client, "guard")

    first = client.post(f"/api/alerts/{alert_id}/acknowledge", headers=headers).json()
    second = client.post(f"/api/alerts/{alert_id}/acknowledge", headers=headers).json()

    assert first["acknowledged_at"] == second["acknowledged_at"]
    assert first["acknowledged_by_id"] == second["acknowledged_by_id"]

    audit_rows = db.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.ALERT_ACKNOWLEDGED)
    ).scalars().all()
    assert len(audit_rows) == 1  # the no-op path writes no second audit row


def test_resident_is_forbidden(client: TestClient, db: Session, resident: User) -> None:
    _seed_alerts(db)
    response = client.get("/api/alerts", headers=auth_headers(client, "tenant"))
    assert response.status_code == 403
