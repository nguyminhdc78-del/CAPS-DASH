"""`/system/*` schemas: the implemented `info` snapshot, plus the frozen
`backup`/`purge` contracts phase 13 implements.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class TableRowCounts(BaseModel):
    """Row counts for the tables an operator cares about at a glance."""

    cameras: int
    parking_slots: int
    slot_state_history: int
    alerts: int
    audit_logs: int
    users: int


class SystemInfoResponse(BaseModel):
    disk_free_bytes: int
    disk_total_bytes: int
    table_row_counts: TableRowCounts
    # "" when the database has no `alembic_version` table yet (a freshly
    # `create_all`-ed database, e.g. in tests) - never a 500 for that.
    schema_revision: str
    uptime_seconds: float
    # True when timestamps written right now cannot be trusted: the target
    # board has no battery-backed clock, so a post-power-cut boot briefly
    # believes it is some date in the past. See `db/clock_guard.py`.
    clock_suspect: bool


class BackupResponse(BaseModel):
    """Phase 13 copies the sqlite file into `settings.backup_dir`."""

    backup_path: str
    size_bytes: int
    created_at: dt.datetime


class PurgeRequest(BaseModel):
    """Deletes history/alert rows older than the retention window.

    Defaults to `settings.retention_months` (6, chosen for flash write
    endurance) when omitted; an explicit value allows a narrower one-off
    purge without changing the standing configuration.

    PHASE-13 ADDITION: `dry_run` did not exist on the schema phase 07 froze,
    but the phase-13 spec is explicit that purge "supports a dry run
    reporting what it would delete" and that "dry-run is the default in the
    UI" - neither is possible without a field to carry the flag. Defaults to
    `True` as a deliberate safety net: a caller that forgets to set it
    deletes nothing, rather than everything.
    """

    older_than_months: int | None = Field(default=None, ge=1, le=60)
    dry_run: bool = True


class PurgeResponse(BaseModel):
    deleted_history_rows: int
    deleted_alert_rows: int
    # PHASE-13 ADDITION, paired with `PurgeRequest.dry_run` above: without an
    # echo of it here, a client that only looks at the counts cannot tell a
    # preview apart from a real deletion.
    dry_run: bool
