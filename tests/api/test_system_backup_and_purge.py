"""`POST /system/backup`, `POST /system/purge`: admin-only, audited, dry-run
default. The backup file itself and integrity checking are covered more
thoroughly in `tests/services/test_backup_produces_valid_db.py`; this module
is the HTTP contract - status codes, RBAC, and that the route wires the
service correctly end to end.
"""

from __future__ import annotations

import datetime as dt

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from caps_dash.db.enums import AuditAction, CameraSourceType, SlotState
from caps_dash.db.models import AuditLog, Camera, ParkingSlot, SlotStateHistory, User
from tests.api.conftest import auth_headers


def _seed_old_and_recent_history(db: Session) -> None:
    now = dt.datetime.now(dt.UTC)
    camera = Camera(code="CAM-A", name="Deck A", floor="B1", source_type=CameraSourceType.FAKE)
    slot = ParkingSlot(code="A1", floor="B1")
    camera.slots = [slot]
    db.add(camera)
    db.commit()
    db.add_all(
        [
            SlotStateHistory(
                slot_id=slot.id, camera_code="CAM-A", slot_code="A1", floor="B1",
                previous_state=SlotState.FREE, new_state=SlotState.OCCUPIED,
                changed_at=now - dt.timedelta(days=400),
            ),
            SlotStateHistory(
                slot_id=slot.id, camera_code="CAM-A", slot_code="A1", floor="B1",
                previous_state=SlotState.OCCUPIED, new_state=SlotState.FREE,
                changed_at=now - dt.timedelta(days=1),
            ),
        ]
    )
    db.commit()


# --- backup ------------------------------------------------------------


def test_backup_creates_a_file_and_audits_it(
    client: TestClient, db: Session, admin: User, app: FastAPI
) -> None:
    response = client.post("/api/system/backup", headers=auth_headers(client, "boss"))

    assert response.status_code == 201
    body = response.json()
    assert body["size_bytes"] > 0
    backup_dir = app.state.caps.settings.backup_dir
    assert (backup_dir / body["backup_path"]).exists()

    audit_row = db.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.BACKUP_CREATED)
    ).scalar_one()
    assert audit_row.username == "boss"


def test_backup_requires_admin(client: TestClient, guard: User) -> None:
    response = client.post("/api/system/backup", headers=auth_headers(client, "guard"))
    assert response.status_code == 403


# --- purge ---------------------------------------------------------------


def test_purge_dry_run_deletes_nothing(client: TestClient, db: Session, admin: User) -> None:
    _seed_old_and_recent_history(db)

    response = client.post(
        "/api/system/purge", json={"dry_run": True}, headers=auth_headers(client, "boss")
    )

    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["deleted_history_rows"] == 1

    remaining = db.execute(select(SlotStateHistory)).scalars().all()
    assert len(remaining) == 2  # dry run deletes nothing


def test_purge_omitted_defaults_to_dry_run(client: TestClient, db: Session, admin: User) -> None:
    """`PurgeRequest.dry_run` defaults to `True` - the safety net for a
    caller that forgets to set it."""
    _seed_old_and_recent_history(db)

    response = client.post("/api/system/purge", json={}, headers=auth_headers(client, "boss"))

    assert response.json()["dry_run"] is True
    assert len(db.execute(select(SlotStateHistory)).scalars().all()) == 2


def test_purge_real_run_deletes_only_old_rows(client: TestClient, db: Session, admin: User) -> None:
    _seed_old_and_recent_history(db)

    response = client.post(
        "/api/system/purge", json={"dry_run": False}, headers=auth_headers(client, "boss")
    )

    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is False
    assert body["deleted_history_rows"] == 1

    remaining = db.execute(select(SlotStateHistory)).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].changed_at > dt.datetime.now(dt.UTC) - dt.timedelta(days=30)

    audit_row = db.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.DATA_PURGED)
    ).scalar_one()
    assert audit_row.username == "boss"
    assert audit_row.after_json is not None
    assert audit_row.after_json["dry_run"] is False


def test_purge_requires_admin(client: TestClient, guard: User) -> None:
    response = client.post("/api/system/purge", json={}, headers=auth_headers(client, "guard"))
    assert response.status_code == 403
