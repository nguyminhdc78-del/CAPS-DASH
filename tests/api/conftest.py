"""Fixtures for API tests: a real app, a real database, real users."""

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
from caps_dash.db.models import Base, User
from caps_dash.security.password_hasher import hash_password

PASSWORD = "correct-horse-battery"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        app_env="dev",
        secret_key="test-signing-key-not-for-production-0123456789",
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        backup_dir=tmp_path / "backups",
        spa_dist_dir=tmp_path / "no-frontend",
        log_json=False,
        # Short window so the rate-limit test does not sleep.
        login_max_attempts=3,
        login_window_s=60,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    # The schema must exist BEFORE the app starts: the camera supervisor reads
    # the cameras table during lifespan, exactly as it does in production
    # after `caps-dash migrate` has run.
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
    del client  # ordering only: ensures the schema exists first
    factory = app.state.caps.require_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def make_user(
    db: Session,
    username: str = "guard",
    role: UserRole = UserRole.SECURITY,
    *,
    is_active: bool = True,
) -> User:
    user = User(
        username=username,
        password_hash=hash_password(PASSWORD),
        display_name=username.title(),
        role=role,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def guard(db: Session) -> User:
    return make_user(db, "guard", UserRole.SECURITY)


@pytest.fixture
def admin(db: Session) -> User:
    return make_user(db, "boss", UserRole.ADMIN)


@pytest.fixture
def resident(db: Session) -> User:
    return make_user(db, "tenant", UserRole.RESIDENT)


def login(client: TestClient, username: str, password: str = PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def auth_headers(client: TestClient, username: str) -> dict[str, str]:
    token = login(client, username).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
