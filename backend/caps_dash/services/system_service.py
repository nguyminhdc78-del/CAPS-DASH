"""Operational status snapshot for `/system/info`.

Everything here is read-only and diagnostic: disk headroom, row counts, the
Alembic schema revision and process uptime. None of it comes from a
repository because none of it is a domain query - it is infrastructure
inspection, the same reason `db/session.py`'s readiness check reaches past the
ORM.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ..api.schemas.system_schemas import SystemInfoResponse, TableRowCounts
from ..config.settings import REPO_ROOT, Settings
from ..db.clock_guard import is_clock_suspect
from ..db.models import Alert, AuditLog, Camera, ParkingSlot, SlotStateHistory, User
from ..db.types import utc_now

# Process-start proxy: this module is imported once, early in application
# startup (via the route module import chain), so "since this was imported"
# is close enough to "since the process started" for an uptime counter that
# only needs to be right to the second.
_PROCESS_STARTED_AT = utc_now()

_COUNT_MODELS: dict[str, type[Any]] = {
    "cameras": Camera,
    "parking_slots": ParkingSlot,
    "slot_state_history": SlotStateHistory,
    "alerts": Alert,
    "audit_logs": AuditLog,
    "users": User,
}


def database_directory(settings: Settings) -> Path:
    """Directory `shutil.disk_usage` should measure.

    Mirrors the sqlite path parsing in `db/engine_factory.py`. Anything other
    than sqlite (a future Postgres deployment) has no local directory to
    measure, so this falls back to the repo's data directory rather than
    raising out of a monitoring endpoint.
    """
    if settings.database_url.startswith("sqlite"):
        path_part = settings.database_url.split("sqlite:///", 1)[-1]
        if path_part and path_part != ":memory:":
            return Path(path_part).resolve().parent
    return (REPO_ROOT / "data").resolve()


def _table_row_counts(session: Session) -> TableRowCounts:
    counts = {
        name: int(session.execute(select(func.count()).select_from(model)).scalar_one())
        for name, model in _COUNT_MODELS.items()
    }
    return TableRowCounts(**counts)


def _schema_revision(session: Session) -> str:
    """Current Alembic revision, or "" when the table does not exist.

    A `Base.metadata.create_all` test database (see `tests/api/conftest.py`)
    has no `alembic_version` table at all - that must read as "unknown", not
    500 the whole endpoint.
    """
    try:
        row = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except OperationalError:
        # The failed SELECT leaves the transaction unusable on SQLite; roll
        # back so the session stays valid for whatever runs after this.
        session.rollback()
        return ""
    return str(row) if row is not None else ""


def get_system_info(session: Session, settings: Settings) -> SystemInfoResponse:
    usage = shutil.disk_usage(database_directory(settings))
    return SystemInfoResponse(
        disk_free_bytes=usage.free,
        disk_total_bytes=usage.total,
        table_row_counts=_table_row_counts(session),
        schema_revision=_schema_revision(session),
        uptime_seconds=(utc_now() - _PROCESS_STARTED_AT).total_seconds(),
        clock_suspect=is_clock_suspect(),
    )
