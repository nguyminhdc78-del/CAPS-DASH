"""`/slots` listing, filters, detail, and admin-only metadata updates."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from caps_dash.db.enums import CameraSourceType, SlotState
from caps_dash.db.models import Camera, ParkingSlot, User
from tests.api.conftest import auth_headers


def _seed_camera_with_slots(db: Session) -> dict[str, ParkingSlot]:
    camera = Camera(code="CAM-1", name="Deck A", floor="B1", source_type=CameraSourceType.FAKE)
    db.add(camera)
    db.commit()

    slots = [
        ParkingSlot(
            camera_id=camera.id,
            code="A1",
            floor="B1",
            current_state=SlotState.FREE,
            polygon_json=[[0, 0], [10, 0], [10, 10], [0, 10]],
            src_frame_width=640,
            src_frame_height=480,
        ),
        ParkingSlot(
            camera_id=camera.id,
            code="A2",
            floor="B1",
            current_state=SlotState.OCCUPIED,
            polygon_json=[[20, 0], [30, 0], [30, 10], [20, 10]],
            src_frame_width=640,
            src_frame_height=480,
        ),
        ParkingSlot(
            camera_id=camera.id,
            code="A3",
            floor="B2",
            current_state=SlotState.UNKNOWN,
            polygon_json=[[40, 0], [50, 0], [50, 10], [40, 10]],
            src_frame_width=640,
            src_frame_height=480,
        ),
    ]
    db.add_all(slots)
    db.commit()
    return {slot.code: slot for slot in slots}


def test_list_slots_is_deterministically_ordered(
    client: TestClient, db: Session, guard: User
) -> None:
    _seed_camera_with_slots(db)
    response = client.get("/api/slots", headers=auth_headers(client, "guard"))

    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 3
    assert [item["code"] for item in page["items"]] == ["A1", "A2", "A3"]


def test_list_slots_filters_by_floor(client: TestClient, db: Session, guard: User) -> None:
    _seed_camera_with_slots(db)
    response = client.get(
        "/api/slots", params={"floor": "B2"}, headers=auth_headers(client, "guard")
    )

    page = response.json()
    assert page["total"] == 1
    assert page["items"][0]["code"] == "A3"


def test_list_slots_filters_by_state(client: TestClient, db: Session, guard: User) -> None:
    _seed_camera_with_slots(db)
    response = client.get(
        "/api/slots", params={"state": "OCCUPIED"}, headers=auth_headers(client, "guard")
    )

    page = response.json()
    assert page["total"] == 1
    assert page["items"][0]["code"] == "A2"


def test_resident_cannot_list_slots(client: TestClient, db: Session, resident: User) -> None:
    _seed_camera_with_slots(db)
    response = client.get("/api/slots", headers=auth_headers(client, "tenant"))
    assert response.status_code == 403


def test_slot_detail_includes_polygon_and_frame_size(
    client: TestClient, db: Session, guard: User
) -> None:
    slots = _seed_camera_with_slots(db)
    response = client.get(
        f"/api/slots/{slots['A1'].id}", headers=auth_headers(client, "guard")
    )

    assert response.status_code == 200
    detail = response.json()
    assert detail["polygon"] == [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]
    assert detail["src_frame_width"] == 640
    assert detail["src_frame_height"] == 480
    assert detail["current_state"] == "FREE"


def test_admin_can_rename_a_slot(client: TestClient, db: Session, admin: User) -> None:
    slots = _seed_camera_with_slots(db)
    response = client.patch(
        f"/api/slots/{slots['A1'].id}",
        headers=auth_headers(client, "boss"),
        json={"code": "A1-new"},
    )

    assert response.status_code == 200
    assert response.json()["code"] == "A1-new"


def test_duplicate_code_within_one_camera_is_a_conflict(
    client: TestClient, db: Session, admin: User
) -> None:
    slots = _seed_camera_with_slots(db)
    response = client.patch(
        f"/api/slots/{slots['A2'].id}", headers=auth_headers(client, "boss"), json={"code": "A3"}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SLOT_CODE_TAKEN"


def test_patch_never_accepts_a_polygon_field(
    client: TestClient, db: Session, admin: User
) -> None:
    """`UpdateSlotRequest` has no polygon field - extra keys are silently ignored,
    not applied. Confirms the geometry stays untouched by this endpoint."""
    slots = _seed_camera_with_slots(db)
    original_polygon = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]
    response = client.patch(
        f"/api/slots/{slots['A1'].id}",
        headers=auth_headers(client, "boss"),
        json={"floor": "B3", "polygon": [[99, 99]]},
    )

    assert response.status_code == 200
    assert response.json()["floor"] == "B3"
    assert response.json()["polygon"] == original_polygon


def test_guard_cannot_patch_a_slot(client: TestClient, db: Session, guard: User) -> None:
    slots = _seed_camera_with_slots(db)
    response = client.patch(
        f"/api/slots/{slots['A2'].id}",
        headers=auth_headers(client, "guard"),
        json={"floor": "B3"},
    )
    assert response.status_code == 403
