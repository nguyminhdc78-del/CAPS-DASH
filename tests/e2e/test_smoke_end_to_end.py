"""One test, the whole product: log in, create a camera, draw its slot map,
let the real camera loop run against a fake source and a scripted detector,
then check the change reached three independent surfaces - the summary
endpoint, the WebSocket stream, and the history table. If this passes, the
seams between vision, workers, the API and the realtime hub are demonstrably
wired together, not just individually unit-tested.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from caps_dash.app_factory import create_app
from caps_dash.config.settings import Settings
from caps_dash.db.engine_factory import create_db_engine
from caps_dash.db.enums import UserRole
from caps_dash.db.models import Base, SlotStateHistory, User
from caps_dash.db.session import create_session_factory
from caps_dash.realtime.frame_protocol import decode_frame_message
from caps_dash.security.password_hasher import hash_password
from caps_dash.vision.detectors.fake_detector import FakeVehicleDetector
from caps_dash.vision.domain import Detection
from caps_dash.workers import inference_runner

pytestmark = pytest.mark.e2e

PASSWORD = "correct-horse-battery"
POLL_INTERVAL_S = 0.05
# Lower-left quadrant of the fake source's 640x480 frame (matches
# tests/workers/test_camera_loop_integration.py, which proves this shape
# alone is enough for the scripted car to land inside it).
SLOT_POLYGON = [[40, 260], [300, 260], [300, 440], [40, 440]]
PARKED_CAR = Detection(x1=120.0, y1=300.0, x2=220.0, y2=430.0, confidence=0.9, label="car")
SUMMARY_POLL_TIMEOUT_S = 8.0
SUMMARY_POLL_INTERVAL_S = 0.1


@pytest.fixture(autouse=True)
def scripted_detector(monkeypatch: pytest.MonkeyPatch):
    """Every inference-pool thread sees the parked car instead of the
    empty-garage default the plain `fake` backend returns."""
    inference_runner.reset_thread_detector()
    monkeypatch.setattr(
        inference_runner,
        "build_detector",
        lambda _settings: FakeVehicleDetector([[PARKED_CAR]]),
    )
    yield
    inference_runner.reset_thread_detector()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        app_env="dev",
        secret_key="smoke-test-signing-key-0123456789ABCDEFGH",
        database_url=f"sqlite:///{tmp_path / 'smoke.db'}",
        backup_dir=tmp_path / "backups",
        spa_dist_dir=tmp_path / "no-frontend",
        detector_backend="fake",
        log_json=False,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    engine = create_db_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        session.add(
            User(
                username="boss",
                password_hash=hash_password(PASSWORD),
                display_name="Boss",
                role=UserRole.ADMIN,
            )
        )
        session.commit()
    engine.dispose()
    return create_app(settings)


def _reconcile_now(app: FastAPI) -> None:
    """Trigger the supervisor's reconcile pass for a camera created after
    startup, from this (synchronous) test thread.

    `CameraSupervisor.start()` reconciles once automatically at lifespan
    startup, which is enough for cameras that already exist in the database
    before the app boots. Nothing in the running app currently consumes
    `ReloadSignals.reconcile_event` afterwards to redo that pass when the API
    calls `request_reconcile()` - a camera created through `POST /api/cameras`
    sets the flag, but nothing is watching it (see camera_service.py /
    reload_signals.py). That looks like a real gap for a later phase to close,
    not something this phase's file ownership lets it fix. Driving the real
    `reconcile()` coroutine directly bridges it here, onto the same loop the
    lifespan captured, without touching the production module that owns it.
    """
    supervisor = app.state.caps.supervisor
    loop = supervisor._loop  # test-only bridge, see docstring above
    asyncio.run_coroutine_threadsafe(supervisor.reconcile(), loop).result(timeout=5)


def _poll_until_occupied(client: TestClient, headers: dict) -> dict:
    deadline = time.monotonic() + SUMMARY_POLL_TIMEOUT_S
    last: dict = {}
    while time.monotonic() < deadline:
        response = client.get("/api/summary", headers=headers)
        assert response.status_code == 200, response.text
        last = response.json()
        if last.get("occupied", 0) >= 1:
            return last
        time.sleep(SUMMARY_POLL_INTERVAL_S)
    raise AssertionError(f"slot never reached OCCUPIED in the summary: {last}")


def test_login_to_camera_to_state_change_to_history(app: FastAPI) -> None:
    with TestClient(app) as client:
        # --- log in -------------------------------------------------------
        login = client.post("/api/auth/login", json={"username": "boss", "password": PASSWORD})
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # --- create a camera (fake source, fast poll for a short test) ----
        created = client.post(
            "/api/cameras",
            headers=headers,
            json={
                "code": "SMOKE-1",
                "source_type": "fake",
                "source_url": "",
                "poll_interval_s": POLL_INTERVAL_S,
                "vote_window": 3,
                "vote_threshold": 2,
            },
        )
        assert created.status_code == 201, created.text
        camera_id = created.json()["id"]

        # --- draw its slot map ---------------------------------------------
        slot_map = client.put(
            f"/api/cameras/{camera_id}/slot-map",
            headers=headers,
            json={
                "src_frame_width": 640,
                "src_frame_height": 480,
                "slots": [{"code": "A1", "polygon": {"points": SLOT_POLYGON}}],
            },
        )
        assert slot_map.status_code == 200, slot_map.text

        _reconcile_now(app)

        # --- the worker ticks; a viewer sees a real frame ------------------
        with client.websocket_connect(f"/ws/cameras/{camera_id}") as websocket:
            websocket.send_json({"type": "auth", "token": token})
            assert websocket.receive_json() == {
                "type": "auth_ok",
                "camera_id": camera_id,
                "role": "admin",
            }
            frame = decode_frame_message(websocket.receive_bytes())
            assert frame.header["camera_id"] == camera_id

        # --- the state change reaches the summary endpoint -----------------
        summary = _poll_until_occupied(client, headers)
        assert summary["occupied"] >= 1
        assert summary["total"] >= 1

        # --- and history recorded the transition ---------------------------
        session_factory = app.state.caps.require_session_factory()
        with session_factory() as session:
            rows = list(session.execute(select(SlotStateHistory)).scalars())
        assert any(row.slot_code == "A1" and row.camera_code == "SMOKE-1" for row in rows)
