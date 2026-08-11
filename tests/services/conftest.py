"""Fixtures for service-layer tests: a real, file-backed database and a
throwaway `Settings`, without going through the HTTP layer.

Mirrors `tests/db/conftest.py`'s `db_session` fixture; kept as a separate
copy rather than a cross-package import so `tests/services/` stays free-
standing (pytest's conftest discovery is directory-scoped, and importing a
sibling package's conftest for one fixture reads worse than the ten lines
below).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from caps_dash.config.settings import Settings
from caps_dash.db.engine_factory import create_db_engine
from caps_dash.db.models import Base
from caps_dash.db.session import create_session_factory


@pytest.fixture
def db_session(tmp_path: Path) -> Iterator[Session]:
    """A throwaway file-backed database with the full schema - a file, not
    `:memory:`, so WAL-mode pragmas behave the same as in production.
    """
    engine = create_db_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="dev",
        secret_key="test-secret-not-used-in-prod-0123456789",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        backup_dir=tmp_path / "backups",
        spa_dist_dir=tmp_path / "no-frontend-here",
        log_json=False,
    )
