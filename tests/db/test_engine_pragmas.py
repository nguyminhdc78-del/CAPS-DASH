"""SQLite must be configured correctly on every connection, not just the first."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from caps_dash.db.engine_factory import create_db_engine


@pytest.fixture
def engine(tmp_path: Path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'pragma.db'}")
    yield engine
    engine.dispose()


def test_wal_mode_is_enabled(engine) -> None:
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"


def test_foreign_keys_are_enforced(engine) -> None:
    """SQLite ships foreign keys OFF. Cascades are silently ignored without this."""
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_busy_timeout_is_set(engine) -> None:
    """Without it, a momentarily locked database raises instead of waiting."""
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def test_synchronous_is_normal(engine) -> None:
    """NORMAL (1) is the correct durability pairing with WAL."""
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA synchronous")).scalar() == 1


def test_pragmas_apply_to_every_connection(engine) -> None:
    """The regression this guards.

    Pragmas are per-connection in SQLite. Applying them once at startup leaves
    every later connection - including each worker thread's - on the defaults,
    which is invisible until a cascade silently fails to fire.
    """
    for _ in range(3):
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
            assert connection.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def test_parent_directory_is_created(tmp_path: Path) -> None:
    """First boot on a fresh board must not fail because data/ is missing."""
    nested = tmp_path / "deep" / "nested" / "caps.db"
    engine = create_db_engine(f"sqlite:///{nested}")
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    engine.dispose()
    assert nested.parent.is_dir()
