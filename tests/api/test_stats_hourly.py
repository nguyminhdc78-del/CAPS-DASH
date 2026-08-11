"""`GET /stats/hourly`: reads pre-aggregated rows, scope filtering, RBAC."""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from caps_dash.db.enums import ScopeType
from caps_dash.db.models import HourlyStat, User
from tests.api.conftest import auth_headers

HOUR = dt.datetime(2026, 8, 11, 8, 0, 0, tzinfo=dt.UTC)


def _seed(db: Session) -> None:
    db.add_all(
        [
            HourlyStat(
                scope_type=ScopeType.SITE, scope_key="", hour_start=HOUR,
                occupied_seconds=1800, free_seconds=1800, unknown_seconds=0,
                change_count=2, peak_occupied=1, slot_count=1,
            ),
            HourlyStat(
                scope_type=ScopeType.FLOOR, scope_key="B1", hour_start=HOUR,
                occupied_seconds=1800, free_seconds=1800, unknown_seconds=0,
                change_count=2, peak_occupied=1, slot_count=1,
            ),
        ]
    )
    db.commit()


def test_default_scope_is_site(client: TestClient, db: Session, guard: User) -> None:
    _seed(db)
    response = client.get(
        "/api/stats/hourly",
        params={"from": (HOUR - dt.timedelta(days=1)).isoformat(), "to": HOUR.isoformat()},
        headers=auth_headers(client, "guard"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["scope_type"] == "site"
    assert body["items"][0]["occupied_seconds"] == 1800


def test_filters_by_scope_type_and_key(client: TestClient, db: Session, guard: User) -> None:
    _seed(db)
    response = client.get(
        "/api/stats/hourly",
        params={
            "scope_type": "floor",
            "scope_key": "B1",
            "from": (HOUR - dt.timedelta(days=1)).isoformat(),
            "to": HOUR.isoformat(),
        },
        headers=auth_headers(client, "guard"),
    )

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["scope_key"] == "B1"


def test_resident_is_forbidden(client: TestClient, db: Session, resident: User) -> None:
    _seed(db)
    response = client.get("/api/stats/hourly", headers=auth_headers(client, "tenant"))
    assert response.status_code == 403
