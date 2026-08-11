"""Engine construction and SQLite pragmas."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event

# Applied to EVERY new connection, because SQLite scopes these per connection,
# not per database. Setting them once at startup would leave every later
# connection - including each worker thread's - running on the defaults.
_PRAGMAS = (
    "PRAGMA journal_mode=WAL",  # readers no longer block on the single writer
    "PRAGMA busy_timeout=5000",  # wait for a lock instead of failing instantly
    "PRAGMA foreign_keys=ON",  # SQLite ships this OFF; cascades need it
    "PRAGMA synchronous=NORMAL",  # the correct durability pairing with WAL
)


def create_db_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Build the engine. SQLite gets pragmas; anything else is left alone."""
    is_sqlite = database_url.startswith("sqlite")

    if is_sqlite:
        _ensure_parent_directory(database_url)

    engine = create_engine(
        database_url,
        echo=echo,
        future=True,
        # Connections are handed between the request threadpool and the worker
        # threads. Safe here because writes are funnelled through one thread.
        connect_args={"check_same_thread": False} if is_sqlite else {},
    )

    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _apply_pragmas(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            try:
                for statement in _PRAGMAS:
                    cursor.execute(statement)
            finally:
                cursor.close()

    return engine


def _ensure_parent_directory(database_url: str) -> None:
    """Create the data directory rather than failing on first boot."""
    path_part = database_url.split("sqlite:///", 1)[-1]
    if not path_part or path_part == ":memory:":
        return
    Path(path_part).parent.mkdir(parents=True, exist_ok=True)
