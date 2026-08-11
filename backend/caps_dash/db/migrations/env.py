"""Alembic environment.

Two things here are load-bearing:

* `render_as_batch=True` - SQLite cannot ALTER a column, drop a constraint, or
  rename much of anything. Batch mode makes Alembic rebuild the table instead.
  Without it the second schema change of this project's life fails.
* The URL comes from application settings, not from alembic.ini, so there is
  one source of truth for where the database lives.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import Connection

from caps_dash.config.settings import get_settings
from caps_dash.db.engine_factory import create_db_engine
from caps_dash.db.models import Base

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    # `-x url=...` wins, so tests and one-off jobs can point elsewhere.
    override = context.get_x_argument(as_dictionary=True).get("url")
    return override or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        # Without these, autogenerate silently ignores type and default
        # changes, and a "no diff" result stops meaning anything.
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_db_engine(_database_url())
    with engine.connect() as connection:
        _run(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
