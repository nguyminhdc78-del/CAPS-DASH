"""`/summary` privacy: counts only, never a slot id, slot code or camera code."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from caps_dash.db.enums import CameraSourceType, SlotState
from caps_dash.db.models import Camera, ParkingSlot, User
from tests.api.conftest import auth_headers


def _seed_camera_with_slots(db: Session) -> Camera:
    camera = Camera(code="CAM-1", name="Deck A", floor="B1", source_type=CameraSourceType.FAKE)
    db.add(camera)
    db.commit()

    db.add_all(
        [
            ParkingSlot(
                camera_id=camera.id, code="A1", floor="B1", current_state=SlotState.FREE
            ),
            ParkingSlot(
                camera_id=camera.id, code="A2", floor="B1", current_state=SlotState.OCCUPIED
            ),
            ParkingSlot(
                camera_id=camera.id, code="A3", floor="B2", current_state=SlotState.UNKNOWN
            ),
        ]
    )
    db.commit()
    return camera


def test_resident_summary_has_no_slot_or_camera_identifiers(
    client: TestClient, db: Session, resident: User
) -> None:
    _seed_camera_with_slots(db)
    response = client.get("/api/summary", headers=auth_headers(client, "tenant"))

    assert response.status_code == 200
    # Raw text, not just parsed keys: a leaked identifier anywhere in the body
    # (a stray debug field, a nested object) is the failure this guards.
    assert "A1" not in response.text
    assert "A2" not in response.text
    assert "A3" not in response.text
    assert "CAM-1" not in response.text


def test_summary_counts_are_correct_and_unknown_is_separate_from_free(
    client: TestClient, db: Session, resident: User
) -> None:
    _seed_camera_with_slots(db)
    body = client.get("/api/summary", headers=auth_headers(client, "tenant")).json()

    assert body["total"] == 3
    assert body["free"] == 1
    assert body["occupied"] == 1
    assert body["unknown"] == 1
    assert body["free"] + body["occupied"] + body["unknown"] == body["total"]

    floor_b1 = next(floor for floor in body["by_floor"] if floor["floor"] == "B1")
    assert floor_b1 == {"floor": "B1", "total": 2, "free": 1, "occupied": 1, "unknown": 0}


def test_admin_sees_the_identical_shape_as_a_resident(
    client: TestClient, db: Session, admin: User
) -> None:
    """Same endpoint, same privacy shape - admin gets no extra fields here.

    Admins reach slot ids and codes through `/slots`, not through `/summary`.
    """
    _seed_camera_with_slots(db)
    body = client.get("/api/summary", headers=auth_headers(client, "boss")).json()

    assert body["total"] == 3
    assert body["free"] == 1
    assert body["occupied"] == 1
    assert body["unknown"] == 1
    assert set(body.keys()) == {"total", "free", "occupied", "unknown", "by_floor", "updated_at"}
