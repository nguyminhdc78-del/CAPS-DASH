"""Database fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from caps_dash.db.engine_factory import create_db_engine
from caps_dash.db.models import Base
from caps_dash.db.session import create_session_factory


@pytest.fixture
def db_session(tmp_path: Path) -> Iterator[Session]:
    """A throwaway file-backed database with the full schema.

    A file rather than :memory: on purpose - the pragmas under test (WAL in
    particular) behave differently for in-memory databases, so testing against
    one would prove nothing about production.
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
