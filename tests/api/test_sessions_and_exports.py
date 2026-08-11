"""`GET /sessions` and `GET /exports/history.csv`: derived sessions and the
streaming CSV, through the real HTTP layer (unit coverage of the derivation
state machine itself lives in `tests/services/test_session_derivation.py`).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from caps_dash.app_factory import create_app
from caps_dash.config.settings import Settings
from caps_dash.db.engine_factory import create_db_engine
from caps_dash.db.enums import CameraSourceType, SlotState
from caps_dash.db.models import Base, Camera, ParkingSlot, SlotStateHistory, User
from tests.api.conftest import auth_headers, make_user

NOW = dt.datetime.now(dt.UTC)


def _seed(db: Session) -> ParkingSlot:
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
                changed_at=NOW - dt.timedelta(hours=2),
            ),
            SlotStateHistory(
                slot_id=slot.id, camera_code="CAM-A", slot_code="A1", floor="B1",
                previous_state=SlotState.OCCUPIED, new_state=SlotState.FREE,
                changed_at=NOW - dt.timedelta(hours=1),
            ),
            # Still open at "now": no matching FREE row.
            SlotStateHistory(
                slot_id=slot.id, camera_code="CAM-A", slot_code="A1", floor="B1",
                previous_state=SlotState.FREE, new_state=SlotState.OCCUPIED,
                changed_at=NOW - dt.timedelta(minutes=10),
            ),
        ]
    )
    db.commit()
    return slot


def test_sessions_lists_a_closed_and_an_ongoing_session(
    client: TestClient, db: Session, guard: User
) -> None:
    _seed(db)
    response = client.get("/api/sessions", headers=auth_headers(client, "guard"))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2

    ongoing = next(item for item in body["items"] if item["ongoing"])
    closed = next(item for item in body["items"] if not item["ongoing"])
    assert ongoing["ended_at"] is None
    assert ongoing["duration_seconds"] > 0  # measured to "now", not left null
    assert closed["ended_at"] is not None
    assert closed["duration_seconds"] == 3600


def test_sessions_filters_by_slot_id(client: TestClient, db: Session, guard: User) -> None:
    slot = _seed(db)
    response = client.get(
        "/api/sessions", params={"slot_id": slot.id}, headers=auth_headers(client, "guard")
    )
    body = response.json()
    assert body["total"] == 2
    assert all(item["slot_id"] == slot.id for item in body["items"])


def test_sessions_resident_is_forbidden(client: TestClient, db: Session, resident: User) -> None:
    _seed(db)
    response = client.get("/api/sessions", headers=auth_headers(client, "tenant"))
    assert response.status_code == 403


def test_export_csv_streams_a_header_and_matching_rows(
    client: TestClient, db: Session, guard: User
) -> None:
    _seed(db)
    response = client.get(
        "/api/exports/history.csv", headers=auth_headers(client, "guard")
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]

    lines = response.text.strip().splitlines()
    assert lines[0].split(",")[0] == "id"
    assert len(lines) == 1 + 3  # header + the three seeded rows


def test_export_csv_over_the_row_cap_is_rejected(tmp_path: Path) -> None:
    """A tiny `max_export_rows` forces the guard to trip without seeding
    thousands of rows - a fresh app instance is built with that override
    rather than mutating the shared `settings` fixture mid-test.
    """
    settings = Settings(
        app_env="dev",
        secret_key="test-signing-key-not-for-production-0123456789",
        database_url=f"sqlite:///{tmp_path / 'export-cap.db'}",
        backup_dir=tmp_path / "backups",
        spa_dist_dir=tmp_path / "no-frontend",
        log_json=False,
        max_export_rows=2,
    )
    engine = create_db_engine(settings.database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    app = create_app(settings)

    with TestClient(app) as client:
        factory = app.state.caps.require_session_factory()
        db_session = factory()
        try:
            make_user(db_session, "guard")
            _seed(db_session)  # writes 3 rows; the cap is 2
        finally:
            db_session.close()

        response = client.get(
            "/api/exports/history.csv", headers=auth_headers(client, "guard")
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RANGE_TOO_WIDE"


def test_export_csv_resident_is_forbidden(client: TestClient, db: Session, resident: User) -> None:
    _seed(db)
    response = client.get("/api/exports/history.csv", headers=auth_headers(client, "tenant"))
    assert response.status_code == 403
