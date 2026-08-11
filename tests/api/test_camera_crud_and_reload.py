"""Camera CRUD, list-with-health, reload/reconcile signalling after commit,
and connection-test round trips - phase 07's camera surface.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import event, select

from caps_dash.db.models import Camera, ParkingSlot
from tests.api.conftest import auth_headers


def _create_camera(client: TestClient, headers: dict, *, code: str, **overrides: object) -> dict:
    payload: dict = {"code": code, "source_type": "fake", "source_url": ""}
    payload.update(overrides)
    response = client.post("/api/cameras", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# --- CRUD, list shape, RBAC ---------------------------------------------


def test_created_camera_appears_in_list_with_zero_slots(client, admin):
    headers = auth_headers(client, "boss")
    created = _create_camera(client, headers, code="CAM-1")

    listed = client.get("/api/cameras", headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["id"] == created["id"]
    assert item["slot_count"] == 0
    # A camera that has not returned a frame yet is never reported online,
    # whether or not a worker has started for it. `online` is what the
    # dashboard colours a row by, so it must mean "answered recently", not
    # "we have a process for this".
    assert item["health"] is None or item["health"]["online"] is False


def test_a_disabled_camera_reports_no_health_at_all(client, admin):
    """None, not a zero-filled object.

    A disabled camera has no worker, so there is nothing to report. Filling in
    zeros would be indistinguishable from a running camera that happens to be
    idle - the distinction this schema exists to keep.
    """
    headers = auth_headers(client, "boss")
    _create_camera(client, headers, code="CAM-OFF", is_enabled=False)

    item = client.get("/api/cameras", headers=headers).json()["items"][0]

    assert item["is_enabled"] is False
    assert item["health"] is None


def test_guard_cannot_create_camera(client, guard):
    headers = auth_headers(client, "guard")
    response = client.post(
        "/api/cameras", headers=headers, json={"code": "CAM-X", "source_type": "fake"}
    )
    assert response.status_code == 403


def test_duplicate_code_is_conflict(client, admin):
    headers = auth_headers(client, "boss")
    _create_camera(client, headers, code="CAM-DUP")
    response = client.post(
        "/api/cameras", headers=headers, json={"code": "CAM-DUP", "source_type": "fake"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CAMERA_CODE_TAKEN"


def test_source_url_credentials_are_stripped_in_every_response(client, admin):
    headers = auth_headers(client, "boss")
    created = _create_camera(
        client,
        headers,
        code="CAM-CRED",
        source_type="esp32cam_http",
        source_url="http://admin:s3cr3t@10.0.0.5/cam.jpg",
    )
    assert created["source_url"] == "http://10.0.0.5/cam.jpg"

    fetched = client.get(f"/api/cameras/{created['id']}", headers=headers)
    assert "s3cr3t" not in fetched.text
    assert fetched.json()["source_url"] == "http://10.0.0.5/cam.jpg"


def test_get_missing_camera_is_404(client, admin):
    headers = auth_headers(client, "boss")
    response = client.get("/api/cameras/999999", headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_create_camera_rejects_vote_threshold_above_window(client, admin):
    headers = auth_headers(client, "boss")
    response = client.post(
        "/api/cameras",
        headers=headers,
        json={"code": "CAM-BADVOTE", "source_type": "fake", "vote_window": 3, "vote_threshold": 5},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


# --- Reload/reconcile signalling, strictly after commit -----------------


def test_update_camera_signals_reload_strictly_after_commit(client, admin):
    headers = auth_headers(client, "boss")
    camera_id = _create_camera(client, headers, code="CAM-RELOAD")["id"]

    reload_signals = client.app.state.caps.services["reload_signals"]
    session_factory = client.app.state.caps.require_session_factory()
    seen: list[float] = []
    original_request = reload_signals.request

    def spy(camera_id_arg: int) -> None:
        # A brand-new session/connection must already see the write - proof
        # the signal fired strictly after `session.commit()`, not before it.
        # If the signal jumped the gun this probe would still read the old
        # `poll_interval_s`, and the assertion below would catch it.
        with session_factory() as probe:
            row = probe.get(Camera, camera_id_arg)
            seen.append(row.poll_interval_s)
        original_request(camera_id_arg)

    reload_signals.request = spy

    response = client.patch(
        f"/api/cameras/{camera_id}", headers=headers, json={"poll_interval_s": 9.5}
    )
    assert response.status_code == 200
    assert seen == [9.5]


def test_delete_camera_cascades_slots_and_signals_reconcile(client, admin, db):
    headers = auth_headers(client, "boss")
    camera_id = _create_camera(client, headers, code="CAM-DEL")["id"]
    put_response = client.put(
        f"/api/cameras/{camera_id}/slot-map",
        headers=headers,
        json={
            "src_frame_width": 640,
            "src_frame_height": 480,
            "slots": [
                {"code": "A1", "polygon": {"points": [[50, 50], [150, 50], [150, 150], [50, 150]]}}
            ],
        },
    )
    assert put_response.status_code == 200

    reload_signals = client.app.state.caps.services["reload_signals"]
    calls: list[str] = []
    reload_signals.request_reconcile = lambda: calls.append("reconcile")

    response = client.delete(f"/api/cameras/{camera_id}", headers=headers)
    assert response.status_code == 200
    assert calls == ["reconcile"]

    remaining = db.execute(
        select(ParkingSlot).where(ParkingSlot.camera_id == camera_id)
    ).scalars().all()
    assert remaining == []


def test_runtime_confidence_is_clamped_and_signals_reload_not_reconcile(client, admin, guard):
    admin_headers = auth_headers(client, "boss")
    camera_id = _create_camera(client, admin_headers, code="CAM-CONF")["id"]

    reload_signals = client.app.state.caps.services["reload_signals"]
    reload_calls: list[int] = []
    reconcile_calls: list[str] = []
    reload_signals.request = lambda camera_id_arg: reload_calls.append(camera_id_arg)
    reload_signals.request_reconcile = lambda: reconcile_calls.append("reconcile")

    # Runtime tuning is `security`-level, not `admin` - a guard must be able
    # to nudge confidence without a login upgrade.
    guard_headers = auth_headers(client, "guard")
    response = client.patch(
        f"/api/cameras/{camera_id}/runtime", headers=guard_headers, json={"confidence": 0.99}
    )
    assert response.status_code == 200
    assert response.json()["confidence"] == 0.95  # clamped to RUNTIME_CONFIDENCE_MAX
    assert reload_calls == [camera_id]
    assert reconcile_calls == []  # tuning must never restart the worker


# --- No N+1 on the list endpoint -----------------------------------------


def test_list_query_count_is_constant_regardless_of_camera_count(client, admin):
    headers = auth_headers(client, "boss")
    engine = client.app.state.caps.engine

    def count_queries_for_list() -> int:
        count = 0

        def _tick(*_args: object, **_kwargs: object) -> None:
            nonlocal count
            count += 1

        event.listen(engine, "before_cursor_execute", _tick)
        try:
            response = client.get("/api/cameras", headers=headers)
            assert response.status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", _tick)
        return count

    _create_camera(client, headers, code="CAM-Q1")
    first_count = count_queries_for_list()

    for i in range(2, 6):
        _create_camera(client, headers, code=f"CAM-Q{i}")
    second_count = count_queries_for_list()

    assert first_count == second_count


# --- Connection test, always HTTP 200 ------------------------------------


def test_connection_test_against_a_dead_source_returns_200_ok_false(client, admin, tmp_path):
    headers = auth_headers(client, "boss")
    response = client.post(
        "/api/cameras/test-connection",
        headers=headers,
        json={"source_type": "image_folder", "source_url": str(tmp_path)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error_code"] == "CAMERA_UNREACHABLE"
