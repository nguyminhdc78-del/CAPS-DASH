"""Audit trail (admin-only, paginated) and `/system/info`.

`/system/backup` and `/system/purge` have their own test module,
`test_system_backup_and_purge.py`, now that phase 13 has implemented them.
"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from caps_dash.db.enums import AuditAction
from caps_dash.db.models import AuditLog, User
from tests.api.conftest import auth_headers


def _seed_audit_rows(db: Session, count: int = 3) -> None:
    now = dt.datetime.now(dt.UTC)
    db.add_all(
        [
            AuditLog(
                username="boss",
                action=AuditAction.USER_UPDATED,
                entity_type="user",
                entity_id=str(i),
                created_at=now - dt.timedelta(minutes=i),
            )
            for i in range(count)
        ]
    )
    db.commit()


# --- Audit trail --------------------------------------------------------


def test_audit_logs_require_admin(client: TestClient, db: Session, guard: User) -> None:
    _seed_audit_rows(db)
    response = client.get("/api/audit-logs", headers=auth_headers(client, "guard"))
    assert response.status_code == 403


def test_audit_logs_are_paginated_for_admin(
    client: TestClient, db: Session, admin: User
) -> None:
    headers = auth_headers(client, "boss")  # this login itself writes a LOGIN audit row
    _seed_audit_rows(db, count=5)

    # Filter to the seeded action so the login's own audit row (unrelated
    # noise for this test) does not throw off the pagination assertions.
    response = client.get(
        "/api/audit-logs", params={"limit": 2, "action": "user_updated"}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["limit"] == 2


# --- System info ---------------------------------------------------------


def test_system_info_returns_plausible_values_on_a_fresh_database(
    client: TestClient, admin: User
) -> None:
    response = client.get("/api/system/info", headers=auth_headers(client, "boss"))

    assert response.status_code == 200
    body = response.json()
    assert body["disk_free_bytes"] > 0
    assert body["disk_total_bytes"] >= body["disk_free_bytes"]
    assert body["table_row_counts"]["users"] >= 1  # at least the admin fixture
    # `Base.metadata.create_all` (this test's schema) never runs Alembic, so
    # there is no `alembic_version` table - that must read as "", not 500.
    assert body["schema_revision"] == ""
    assert body["uptime_seconds"] >= 0
    assert isinstance(body["clock_suspect"], bool)


def test_system_info_requires_admin(client: TestClient, guard: User) -> None:
    response = client.get("/api/system/info", headers=auth_headers(client, "guard"))
    assert response.status_code == 403
