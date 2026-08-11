"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from caps_dash.app_factory import create_app
from caps_dash.config.settings import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Dev-profile settings pointed at a throwaway directory.

    Built explicitly rather than via get_settings() so tests never read the
    developer's own .env, and never share the lru_cache with another test.
    """
    return Settings(
        app_env="dev",
        secret_key="test-secret-not-used-in-prod-0123456789",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        backup_dir=tmp_path / "backups",
        spa_dist_dir=tmp_path / "no-frontend-here",
        log_json=False,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
