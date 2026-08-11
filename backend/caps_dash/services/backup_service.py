"""Database backups via SQLite's online backup API.

Copying the file while WAL is active can capture a torn write mid-transaction
and restore as corruption - the reference project's likely bug (see phase-13
plan, "Backup (correct form)"). `sqlite3.Connection.backup()` instead copies
pages under SQLite's own consistency guarantees while the database stays
live, so backing up never has to stop or block the writer.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..api.schemas.system_schemas import BackupResponse
from ..config.settings import Settings
from ..db.enums import AuditAction
from ..db.types import utc_now
from ..errors.codes import ErrorCode
from ..errors.exceptions import AppError
from ..observability.logging_setup import get_logger
from . import audit_service

logger = get_logger(__name__)

BACKUP_GLOB = "caps-*.db"


def create_backup(engine: Engine, backup_dir: Path) -> Path:
    """Take a consistent snapshot of the live database into `backup_dir`.

    The filename carries microseconds, not just seconds - two backups
    requested moments apart (a retried click, a fast test loop) land on the
    same second-resolution name otherwise, and the second one silently
    overwrites the first instead of producing two files to rotate between.
    """
    target = backup_dir / f"caps-{utc_now():%Y%m%d-%H%M%S-%f}.db"
    backup_dir.mkdir(parents=True, exist_ok=True)

    raw = engine.raw_connection()
    try:
        driver_connection = raw.driver_connection
        if driver_connection is None:
            raise AppError(
                "No active database connection to back up",
                code=ErrorCode.BACKUP_FAILED,
                status_code=500,
            )
        destination = sqlite3.connect(target)
        try:
            driver_connection.backup(destination)
        finally:
            destination.close()
    finally:
        raw.close()
    return target


def verify_backup(path: Path) -> None:
    """`PRAGMA integrity_check` on the finished file before trusting it.

    An unopened backup is a promise, not a backup. This is the cheap way to
    catch a corrupt result (a full disk mid-copy, a truncated write) before
    an operator discovers it during a real restore.
    """
    connection = sqlite3.connect(path)
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.DatabaseError as exc:
        # Not just a failed check - the file is not even openable as a
        # database (e.g. truncated mid-write by a full disk). Same
        # conclusion either way: the backup cannot be trusted.
        raise AppError(
            f"Backup failed integrity check: {exc}",
            code=ErrorCode.BACKUP_FAILED,
            status_code=500,
        ) from exc
    finally:
        connection.close()
    if row is None or row[0] != "ok":
        raise AppError(
            f"Backup failed integrity check: {row}",
            code=ErrorCode.BACKUP_FAILED,
            status_code=500,
        )


def rotate_backups(backup_dir: Path, keep_count: int) -> list[Path]:
    """Delete backups beyond the newest `keep_count`.

    Filenames sort chronologically (`caps-YYYYMMDD-HHMMSS.db`), so a plain
    name sort is a correct time sort without a `stat()` call per file.
    """
    if keep_count <= 0:
        return []
    existing = sorted(backup_dir.glob(BACKUP_GLOB))
    stale = existing[:-keep_count] if len(existing) > keep_count else []
    for path in stale:
        path.unlink(missing_ok=True)
    return stale


def create_backup_and_audit(
    engine: Engine,
    factory: sessionmaker[Session],
    settings: Settings,
    *,
    actor_username: str,
    actor_user_id: int | None = None,
    client_ip: str = "",
) -> BackupResponse:
    """Backup, verify, rotate, audit - the whole operation.

    Intended to run inside the single-writer DB executor (`lifespan.py`'s
    `db_pool`) so it never contends with the camera worker's writes and never
    blocks the event loop; the caller (route or CLI command) is responsible
    for that placement, since this function itself is plain sync code.
    """
    path = create_backup(engine, settings.backup_dir)
    verify_backup(path)
    removed = rotate_backups(settings.backup_dir, settings.backup_keep_count)
    size_bytes = path.stat().st_size
    created_at = utc_now()

    session = factory()
    try:
        audit_service.record(
            session,
            action=AuditAction.BACKUP_CREATED,
            username=actor_username,
            user_id=actor_user_id,
            entity_type="backup",
            entity_id=path.name,
            after={"size_bytes": size_bytes, "rotated_out": [p.name for p in removed]},
            client_ip=client_ip,
        )
        session.commit()
    finally:
        session.close()

    logger.info("backup_created", path=path.name, size_bytes=size_bytes, rotated=len(removed))
    # Filename only, never the absolute path: `system/info` and this response
    # are admin-only but still reach a browser, and the directory layout is
    # not something worth exposing there (Security Considerations, phase 13).
    return BackupResponse(backup_path=path.name, size_bytes=size_bytes, created_at=created_at)
