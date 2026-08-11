"""Fixtures for the WebSocket suite: a real app, a real camera, real tokens."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from caps_dash.app_factory import create_app
from caps_dash.config.settings import Settings
from caps_dash.db.engine_factory import create_db_engine
from caps_dash.db.enums import UserRole
from caps_dash.db.models import Base, Camera, User
from caps_dash.security.password_hasher import hash_password

PASSWORD = "correct-horse-battery"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        app_env="dev",
        secret_key="test-signing-key-not-for-production-0123456789",
        database_url=f"sqlite:///{tmp_path / 'ws.db'}",
        backup_dir=tmp_path / "backups",
        spa_dist_dir=tmp_path / "no-frontend",
        log_json=False,
        # Short enough that the deadline test does not stall the suite for
        # five seconds, long enough that a normal handshake still fits.
        ws_auth_deadline_s=0.3,
        # Far longer than any test takes. A short heartbeat would interleave
        # server pings with the messages each test is asserting on, making the
        # suite flaky for reasons that have nothing to do with the code under
        # test; `Heartbeat` is unit-tested directly instead.
        ws_heartbeat_s=30.0,
        ws_max_viewers_per_camera=2,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    engine = create_db_engine(settings.database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db(app: FastAPI, client: TestClient) -> Iterator[Session]:
    del client  # ordering only
    factory = app.state.caps.require_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def make_user(db: Session, username: str, role: UserRole) -> User:
    user = User(
        username=username,
        password_hash=hash_password(PASSWORD),
        display_name=username.title(),
        role=role,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def camera(db: Session) -> Camera:
    """A camera with a source that never produces frames.

    The stream endpoint only needs the row to exist and be enabled; frames are
    published by the hub directly in these tests, which keeps them free of the
    detector and of real timing.
    """
    row = Camera(code="C1", name="Ramp", floor="B1", source_type="fake", source_url="")
    db.add(row)
    db.commit()
    return row


def access_token(client: TestClient, username: str) -> str:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": PASSWORD}
    )
    token: str = response.json()["access_token"]
    return token
