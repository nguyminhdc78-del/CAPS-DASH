"""The LED-ring commissioning endpoint.

The device is stubbed. What matters here is that an installer standing in
front of a ring is told the truth: a bad pattern never reaches the device, a
node that answers but has no ring says so distinctly from one that cannot be
reached at all, and a guard cannot drive the lamp.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from caps_dash.db.enums import CameraSourceType
from caps_dash.db.models import Camera
from caps_dash.services import slot_led_service
from tests.api.conftest import auth_headers


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


def _stub_ring(
    monkeypatch: pytest.MonkeyPatch, reply: httpx.Response | Exception
) -> list[str]:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["slots"])
        if isinstance(reply, Exception):
            raise reply
        return reply

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def patched(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(slot_led_service.httpx, "AsyncClient", patched)
    return seen


@pytest.fixture
def ring(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return _stub_ring(monkeypatch, httpx.Response(200, json={"ok": True}))


def test_a_pattern_reaches_the_device_and_the_reply_says_when_it_reverts(
    client: TestClient, admin, camera, ring
):
    # The revert window is stated by the server rather than assumed in the UI,
    # so the notice cannot drift away from REFRESH_S.
    response = client.post(
        "/api/cameras/1/ring-test", headers=auth_headers(client, "boss"), json={"slots": "1"}
    )

    assert response.status_code == 200
    assert ring == ["1"]
    assert response.json()["reverts_within_s"] == slot_led_service.REFRESH_S


def test_a_pattern_outside_the_alphabet_never_reaches_the_device(
    client: TestClient, admin, camera, ring
):
    response = client.post(
        "/api/cameras/1/ring-test", headers=auth_headers(client, "boss"), json={"slots": "1x0"}
    )

    assert response.status_code == 422
    assert ring == []


def test_a_node_without_a_ring_is_told_apart_from_one_that_is_unreachable(
    client: TestClient, admin, camera, monkeypatch: pytest.MonkeyPatch
):
    # A 404 means the device is alive and answering, just not running firmware
    # with a ring - the difference between checking the wiring and checking
    # what is flashed on it.
    _stub_ring(monkeypatch, httpx.Response(404))

    response = client.post(
        "/api/cameras/1/ring-test", headers=auth_headers(client, "boss"), json={"slots": "0"}
    )

    assert response.status_code >= 400
    assert response.json()["error"]["code"] == "CAMERA_SOURCE_INVALID"


def test_an_unreachable_node_reports_as_such(
    client: TestClient, admin, camera, monkeypatch: pytest.MonkeyPatch
):
    _stub_ring(monkeypatch, httpx.ConnectError("no route to host"))

    response = client.post(
        "/api/cameras/1/ring-test", headers=auth_headers(client, "boss"), json={"slots": "0"}
    )

    assert response.status_code >= 400
    assert response.json()["error"]["code"] == "CAMERA_UNREACHABLE"


def test_a_guard_cannot_drive_the_lamp(client: TestClient, guard, camera, ring):
    response = client.post(
        "/api/cameras/1/ring-test", headers=auth_headers(client, "guard"), json={"slots": "1"}
    )

    assert response.status_code == 403
    assert ring == []
