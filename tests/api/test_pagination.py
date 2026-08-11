"""Offset pagination via `/slots`: limit/offset slicing, total count, server cap."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from caps_dash.db.enums import CameraSourceType, SlotState
from caps_dash.db.models import Camera, ParkingSlot, User
from tests.api.conftest import auth_headers

SLOT_COUNT = 7


def _seed_many_slots(db: Session) -> None:
    camera = Camera(code="CAM-1", name="Deck A", floor="B1", source_type=CameraSourceType.FAKE)
    db.add(camera)
    db.commit()

    db.add_all(
        [
            ParkingSlot(
                camera_id=camera.id, code=f"S{i:02d}", floor="B1", current_state=SlotState.FREE
            )
            for i in range(SLOT_COUNT)
        ]
    )
    db.commit()


def test_limit_and_offset_slice_the_result(client: TestClient, db: Session, guard: User) -> None:
    _seed_many_slots(db)
    headers = auth_headers(client, "guard")

    first_page = client.get("/api/slots", params={"limit": 3, "offset": 0}, headers=headers).json()
    second_page = client.get(
        "/api/slots", params={"limit": 3, "offset": 3}, headers=headers
    ).json()

    assert [item["code"] for item in first_page["items"]] == ["S00", "S01", "S02"]
    assert [item["code"] for item in second_page["items"]] == ["S03", "S04", "S05"]


def test_total_is_the_unfiltered_by_page_count(
    client: TestClient, db: Session, guard: User
) -> None:
    _seed_many_slots(db)
    body = client.get(
        "/api/slots", params={"limit": 2, "offset": 0}, headers=auth_headers(client, "guard")
    ).json()

    assert body["total"] == SLOT_COUNT
    assert len(body["items"]) == 2
    assert body["limit"] == 2
    assert body["offset"] == 0


def test_default_limit_and_offset_when_omitted(
    client: TestClient, db: Session, guard: User
) -> None:
    _seed_many_slots(db)
    body = client.get("/api/slots", headers=auth_headers(client, "guard")).json()

    assert body["limit"] == 50  # pagination.DEFAULT_LIMIT
    assert body["offset"] == 0
    assert len(body["items"]) == SLOT_COUNT  # fewer rows than the default limit


def test_limit_above_the_server_cap_is_rejected(
    client: TestClient, db: Session, guard: User
) -> None:
    _seed_many_slots(db)
    response = client.get(
        "/api/slots", params={"limit": 500}, headers=auth_headers(client, "guard")
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_negative_offset_is_rejected(client: TestClient, db: Session, guard: User) -> None:
    _seed_many_slots(db)
    response = client.get(
        "/api/slots", params={"offset": -1}, headers=auth_headers(client, "guard")
    )
    assert response.status_code == 422
