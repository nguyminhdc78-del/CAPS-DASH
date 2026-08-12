"""Sensor settings: validation, the exposure-lock shorthand, and the audit row.

The device itself is stubbed. What matters here is everything around it -
that a bad value is rejected by name before a request is made, that
`lock_exposure` expands to the three flags the driver actually has, and that
changing a camera's optics is auditable like any other mutation.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from caps_dash.db.enums import CameraSourceType
from caps_dash.db.models import AuditLog, Camera
from caps_dash.services import camera_control_service
from tests.api.conftest import auth_headers

DEVICE_STATUS = {
    "code": "cam-01",
    "rssi": -48,
    "framesize": 8,
    "quality": 12,
    "brightness": 0,
    "aec": 1,
    "agc": 1,
    "awb": 1,
}


@pytest.fixture
def camera(db: Session) -> Camera:
    row = Camera(
        code="01",
        source_type=CameraSourceType.ESP32CAM_HTTP,
        source_url="http://192.0.2.10/anh",
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def device(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    """Stub the camera. Records every /control call so tests can assert on them."""
    calls: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/status":
            return httpx.Response(200, json=DEVICE_STATUS)
        if request.url.path == "/control":
            calls.append(dict(request.url.params))
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def patched(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(camera_control_service.httpx, "AsyncClient", patched)
    return calls


def test_reading_settings_reports_what_the_device_says(client: TestClient, guard, camera, device):
    response = client.get("/api/cameras/1/settings", headers=auth_headers(client, "guard"))

    assert response.status_code == 200
    assert response.json()["settings"]["rssi"] == -48
    assert response.json()["camera_id"] == 1


def test_lock_exposure_expands_to_three_sensor_flags(
    client: TestClient, admin, camera, device
):
    """`aec`, `agc` and `awb` are one operator decision, three driver flags.

    Left on automatic the sensor hunts and the whole frame shifts brightness
    between shots, which the change gate reads as motion - so this shorthand
    is the difference between YOLO running on 11% of frames and on all of them.
    """
    response = client.patch(
        "/api/cameras/1/settings",
        headers=auth_headers(client, "boss"),
        json={"lock_exposure": True},
    )

    assert response.status_code == 200
    assert {call["var"]: call["val"] for call in device} == {"aec": "0", "agc": "0", "awb": "0"}


def test_an_explicit_flag_wins_over_the_shorthand(client: TestClient, admin, camera, device):
    """Someone who sends both meant the specific one."""
    client.patch(
        "/api/cameras/1/settings",
        headers=auth_headers(client, "boss"),
        json={"lock_exposure": True, "awb": 1},
    )

    assert {call["var"]: call["val"] for call in device}["awb"] == "1"


def test_an_out_of_range_value_is_rejected_before_the_device_is_touched(
    client: TestClient, admin, camera, device
):
    """The firmware answers a bad value with a bare 400 that names nothing."""
    response = client.patch(
        "/api/cameras/1/settings",
        headers=auth_headers(client, "boss"),
        json={"brightness": 9},
    )

    assert response.status_code == 422
    assert device == []


def test_changing_the_optics_is_audited(client: TestClient, admin, camera, device, db: Session):
    """A slot reading wrong after somebody dropped the exposure should be
    traceable to that change, like any other mutation."""
    client.patch(
        "/api/cameras/1/settings",
        headers=auth_headers(client, "boss"),
        json={"brightness": 2},
    )

    entry = db.execute(
        select(AuditLog).where(AuditLog.entity_type == "camera_sensor")
    ).scalar_one()
    assert entry.username == "boss"
    assert entry.after_json is not None
    assert entry.after_json["changes"] == {"brightness": 2}


def test_a_guard_cannot_change_settings(client: TestClient, guard, camera, device):
    response = client.patch(
        "/api/cameras/1/settings",
        headers=auth_headers(client, "guard"),
        json={"brightness": 1},
    )

    assert response.status_code == 403
    assert device == []


def test_a_source_without_a_sensor_is_refused(client: TestClient, admin, db: Session, device):
    """A folder of images has no optics to tune; say so rather than time out."""
    db.add(Camera(code="folder", source_type=CameraSourceType.IMAGE_FOLDER, source_url="frames"))
    db.commit()

    response = client.get("/api/cameras/1/settings", headers=auth_headers(client, "boss"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CAMERA_SOURCE_INVALID"


def test_settings_are_remembered_for_the_next_restart(
    client: TestClient, admin, camera, device, db: Session
):
    """The device keeps these in RAM only.

    A power blip reverts the exposure lock to automatic, an unlocked sensor
    hunts, and the change gate reads that as motion - taking inference from a
    small fraction of frames to nearly all of them, with nothing reporting a
    problem. The worker re-applies this row when it (re)starts, so what
    matters here is that the intent was persisted at all.
    """
    client.patch(
        "/api/cameras/1/settings",
        headers=auth_headers(client, "boss"),
        json={"lock_exposure": True, "brightness": 1},
    )

    db.refresh(camera)
    assert camera.sensor_settings_json == {
        "brightness": 1,
        "aec": 0,
        "agc": 0,
        "awb": 0,
    }


def test_remembering_merges_rather_than_replaces(
    client: TestClient, admin, camera, device, db: Session
):
    """Changing one slider must not forget the exposure lock."""
    headers = auth_headers(client, "boss")
    client.patch("/api/cameras/1/settings", headers=headers, json={"lock_exposure": True})
    client.patch("/api/cameras/1/settings", headers=headers, json={"contrast": 2})

    db.refresh(camera)
    assert camera.sensor_settings_json["aec"] == 0
    assert camera.sensor_settings_json["contrast"] == 2
