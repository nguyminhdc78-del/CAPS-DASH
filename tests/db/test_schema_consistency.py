"""Schema-level invariants: migrations match models, enums match the domain."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine

from caps_dash.cli.migrate_command import alembic_config
from caps_dash.db.engine_factory import create_db_engine
from caps_dash.db.enums import SlotState as DbSlotState
from caps_dash.db.models import Base
from caps_dash.vision.domain import SlotState as DomainSlotState


def test_domain_and_db_slot_state_stay_in_step() -> None:
    """Two enums on purpose - the domain must never import the ORM.

    The cost of that separation is a chance to drift, so it is pinned here.
    """
    assert {m.name for m in DomainSlotState} == {m.name for m in DbSlotState}
    assert {m.value for m in DomainSlotState} == {m.value for m in DbSlotState}


def _migrated_engine(tmp_path: Path) -> Engine:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    config = alembic_config()
    config.cmd_opts = None
    config.set_main_option("sqlalchemy.url", url)
    # env.py prefers the -x override, which is how a test points elsewhere.
    config.cmd_opts = type("Opts", (), {"x": [f"url={url}"]})()
    command.upgrade(config, "head")
    return create_db_engine(url)


def test_migrations_produce_exactly_the_model_schema(tmp_path: Path) -> None:
    """Guards the classic drift: a model edited without a matching migration.

    Both then work on a developer's machine, because tests build the schema
    from metadata - and the deployed board, which only ever runs migrations,
    gets a different database.
    """
    engine = _migrated_engine(tmp_path)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={"compare_type": True, "render_as_batch": True},
            )
            diff = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert diff == [], f"models and migrations disagree: {diff}"


def test_every_model_is_registered_for_autogenerate() -> None:
    """A model missing from db/models/__init__.py is invisible to Alembic.

    Its table then never appears in a migration, and nothing complains until
    the first query against it fails on a deployed box.
    """
    expected = {
        "users",
        "refresh_sessions",
        "cameras",
        "parking_slots",
        "slot_state_history",
        "hourly_stats",
        "alerts",
        "audit_logs",
    }
    assert expected <= set(Base.metadata.tables)
