"""Alembic environment.

Three things here are load-bearing:

* `render_as_batch=True` - SQLite cannot ALTER a column, drop a constraint, or
  rename much of anything. Batch mode makes Alembic rebuild the table instead.
  Without it the second schema change of this project's life fails.
* **Foreign keys are OFF while migrations run.** This is not a shortcut; it is
  what makes batch mode safe. A batch rebuild is `CREATE TABLE tmp` ->
  `INSERT SELECT` -> `DROP TABLE cameras` -> `RENAME`, and with foreign keys
  enforced that DROP cascades: every `parking_slots` row referencing a camera
  is deleted, and their `slot_state_history` with them. A schema change that
  touches no data would silently destroy all of it. SQLite's own documentation
  for "making other kinds of table schema changes" says to disable foreign
  keys for exactly this reason. Learned the hard way - it wiped a live board's
  slot map.
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
        # SQLite ignores this pragma inside a transaction, so it has to run
        # before one opens - and the `commit()` immediately after is just as
        # load-bearing. Issuing the pragma itself begins an implicit
        # transaction; leaving it open means Alembic's own transaction nests
        # inside it and never commits, so the schema changes apply but the
        # `alembic_version` row is rolled back at close. The database then
        # looks migrated while claiming it is not, and the next `migrate` run
        # tries to create tables that already exist.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        try:
            _run(connection)
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
