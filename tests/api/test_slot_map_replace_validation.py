"""Slot-map bulk replace: upsert-by-code, `allow_delete`, and validation."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from caps_dash.db.models import ParkingSlot
from tests.api.conftest import auth_headers


def _square(x: float, y: float, side: float) -> list[list[float]]:
    return [[x, y], [x + side, y], [x + side, y + side], [x, y + side]]


def _create_camera(client: TestClient, headers: dict) -> int:
    response = client.post(
        "/api/cameras",
        headers=headers,
        json={"code": "CAM-SLOTMAP", "source_type": "fake", "source_url": ""},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _put_map(client: TestClient, headers: dict, camera_id: int, body: dict) -> httpx.Response:
    return client.put(f"/api/cameras/{camera_id}/slot-map", headers=headers, json=body)


@pytest.fixture
def camera_id(client: TestClient, admin) -> int:
    return _create_camera(client, auth_headers(client, "boss"))


# --- Upsert by code preserves ids and history ----------------------------


def test_replace_preserves_slot_ids_for_unchanged_codes(client, admin, camera_id, db):
    headers = auth_headers(client, "boss")
    first = _put_map(
        client,
        headers,
        camera_id,
        {
            "src_frame_width": 1600,
            "src_frame_height": 900,
            "slots": [
                {"code": "A1", "polygon": {"points": _square(100, 100, 200)}},
                {"code": "A2", "polygon": {"points": _square(400, 100, 200)}},
            ],
        },
    )
    assert first.status_code == 200
    ids_before = {
        row.code: row.id
        for row in db.execute(
            select(ParkingSlot).where(ParkingSlot.camera_id == camera_id)
        ).scalars()
    }

    # Second replace: A1 moves, A2 unchanged, A3 is new. No code disappears,
    # so this does not need `allow_delete`.
    second = _put_map(
        client,
        headers,
        camera_id,
        {
            "src_frame_width": 1600,
            "src_frame_height": 900,
            "slots": [
                {"code": "A1", "polygon": {"points": _square(150, 150, 200)}},
                {"code": "A2", "polygon": {"points": _square(400, 100, 200)}},
                {"code": "A3", "polygon": {"points": _square(700, 100, 200)}},
            ],
        },
    )
    assert second.status_code == 200
    ids_after = {
        row.code: row.id
        for row in db.execute(
            select(ParkingSlot).where(ParkingSlot.camera_id == camera_id)
        ).scalars()
    }

    assert ids_after["A1"] == ids_before["A1"]
    assert ids_after["A2"] == ids_before["A2"]
    assert "A3" in ids_after


def test_replace_stores_the_frame_dimensions_it_was_drawn_on(client, admin, camera_id):
    headers = auth_headers(client, "boss")
    response = _put_map(
        client,
        headers,
        camera_id,
        {
            "src_frame_width": 1600,
            "src_frame_height": 900,
            "slots": [{"code": "A1", "polygon": {"points": _square(100, 100, 200)}}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["src_frame_width"] == 1600
    assert body["src_frame_height"] == 900

    fetched = client.get(f"/api/cameras/{camera_id}/slot-map", headers=headers)
    assert fetched.json()["src_frame_width"] == 1600
    assert fetched.json()["src_frame_height"] == 900


# --- allow_delete gate ----------------------------------------------------


def test_replace_without_allow_delete_rejects_a_disappearing_code(client, admin, camera_id):
    headers = auth_headers(client, "boss")
    _put_map(
        client,
        headers,
        camera_id,
        {
            "src_frame_width": 1600,
            "src_frame_height": 900,
            "slots": [
                {"code": "A1", "polygon": {"points": _square(100, 100, 200)}},
                {"code": "A2", "polygon": {"points": _square(400, 100, 200)}},
            ],
        },
    )

    response = _put_map(
        client,
        headers,
        camera_id,
        {
            "src_frame_width": 1600,
            "src_frame_height": 900,
            "slots": [{"code": "A1", "polygon": {"points": _square(100, 100, 200)}}],
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SLOT_MAP_INVALID"


def test_replace_with_allow_delete_removes_the_disappearing_code(client, admin, camera_id, db):
    headers = auth_headers(client, "boss")
    _put_map(
        client,
        headers,
        camera_id,
        {
            "src_frame_width": 1600,
            "src_frame_height": 900,
            "slots": [
                {"code": "A1", "polygon": {"points": _square(100, 100, 200)}},
                {"code": "A2", "polygon": {"points": _square(400, 100, 200)}},
            ],
        },
    )

    response = _put_map(
        client,
        headers,
        camera_id,
        {
            "src_frame_width": 1600,
            "src_frame_height": 900,
            "slots": [{"code": "A1", "polygon": {"points": _square(100, 100, 200)}}],
            "allow_delete": True,
        },
    )
    assert response.status_code == 200
    codes = {row.code for row in db.execute(
        select(ParkingSlot).where(ParkingSlot.camera_id == camera_id)
    ).scalars()}
    assert codes == {"A1"}


# --- Validation ------------------------------------------------------------


def test_replace_rejects_a_point_outside_the_declared_frame(client, admin, camera_id):
    headers = auth_headers(client, "boss")
    response = _put_map(
        client,
        headers,
        camera_id,
        {
            "src_frame_width": 640,
            "src_frame_height": 480,
            "slots": [
                {
                    "code": "A1",
                    "polygon": {"points": [[100, 100], [700, 100], [700, 300], [100, 300]]},
                }
            ],
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SLOT_MAP_FRAME_MISMATCH"


def test_replace_rejects_duplicate_codes_within_the_request(client, admin, camera_id):
    headers = auth_headers(client, "boss")
    response = _put_map(
        client,
        headers,
        camera_id,
        {
            "src_frame_width": 640,
            "src_frame_height": 480,
            "slots": [
                {"code": "A1", "polygon": {"points": _square(50, 50, 100)}},
                {"code": "A1", "polygon": {"points": _square(200, 50, 100)}},
            ],
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SLOT_CODE_TAKEN"


def test_guard_cannot_replace_slot_map(client, guard, camera_id):
    headers = auth_headers(client, "guard")
    response = _put_map(
        client,
        headers,
        camera_id,
        {
            "src_frame_width": 640,
            "src_frame_height": 480,
            "slots": [{"code": "A1", "polygon": {"points": _square(50, 50, 100)}}],
        },
    )
    assert response.status_code == 403


def test_a_degenerate_polygon_reports_its_own_error_code(client, admin, camera_id):
    """Not a generic validation failure.

    The ROI editor has to tell the operator what is wrong with the shape they
    just drew; `VALIDATION_FAILED` cannot distinguish a collinear polygon from
    a missing field.
    """
    headers = auth_headers(client, "boss")
    collinear = [[0.0, 0.0], [10.0, 10.0], [20.0, 20.0]]

    response = _put_map(
        client,
        headers,
        camera_id,
        {
            "src_frame_width": 640,
            "src_frame_height": 480,
            "slots": [{"code": "A1", "floor": "B1", "polygon": {"points": collinear}}],
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "POLYGON_DEGENERATE"
