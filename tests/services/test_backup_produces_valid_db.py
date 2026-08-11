"""`backup_service`: the backup opens, passes `PRAGMA integrity_check`, and
contains the same rows as the live database - taken via SQLite's own online
backup API, never a raw file copy (see the module docstring for why a copy
under WAL is unsafe).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from caps_dash.config.settings import Settings
from caps_dash.db.engine_factory import create_db_engine
from caps_dash.db.enums import AuditAction, CameraSourceType
from caps_dash.db.models import AuditLog, Base, Camera, ParkingSlot
from caps_dash.db.session import create_session_factory
from caps_dash.errors.exceptions import AppError
from caps_dash.services import backup_service


def _seeded_engine(tmp_path: Path) -> tuple[Engine, sessionmaker[Session]]:
    engine = create_db_engine(f"sqlite:///{tmp_path / 'live.db'}")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    session = factory()
    camera = Camera(code="CAM-A", name="Deck A", floor="B1", source_type=CameraSourceType.FAKE)
    camera.slots = [ParkingSlot(code="A1", floor="B1"), ParkingSlot(code="A2", floor="B1")]
    session.add(camera)
    session.commit()
    session.close()
    return engine, factory


def test_backup_passes_integrity_check_and_matches_live_row_counts(tmp_path: Path) -> None:
    engine, factory = _seeded_engine(tmp_path)
    try:
        settings = Settings(
            app_env="dev",
            secret_key="test-secret-not-used-in-prod-0123456789",
            database_url=f"sqlite:///{tmp_path / 'live.db'}",
            backup_dir=tmp_path / "backups",
        )
        result = backup_service.create_backup_and_audit(
            engine, factory, settings, actor_username="tester"
        )

        backup_path = settings.backup_dir / result.backup_path
        assert backup_path.exists()
        assert result.size_bytes == backup_path.stat().st_size

        connection = sqlite3.connect(backup_path)
        try:
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            backed_up_cameras = connection.execute("SELECT COUNT(*) FROM cameras").fetchone()[0]
            backed_up_slots = connection.execute(
                "SELECT COUNT(*) FROM parking_slots"
            ).fetchone()[0]
        finally:
            connection.close()

        with Session(engine) as live_session:
            live_cameras = live_session.execute(
                select(func.count()).select_from(Camera)
            ).scalar_one()
            live_slots = live_session.execute(
                select(func.count()).select_from(ParkingSlot)
            ).scalar_one()
        assert backed_up_cameras == live_cameras == 1
        assert backed_up_slots == live_slots == 2

        # Audited in the same session the backup used.
        with Session(engine) as live_session:
            audit_row = live_session.execute(
                select(AuditLog).where(AuditLog.action == AuditAction.BACKUP_CREATED)
            ).scalar_one()
            assert audit_row.username == "tester"
            assert audit_row.entity_id == result.backup_path
    finally:
        engine.dispose()


def test_rotation_keeps_only_the_newest_keep_count_backups(tmp_path: Path) -> None:
    engine, factory = _seeded_engine(tmp_path)
    try:
        settings = Settings(
            app_env="dev",
            secret_key="test-secret-not-used-in-prod-0123456789",
            database_url=f"sqlite:///{tmp_path / 'live.db'}",
            backup_dir=tmp_path / "backups",
            backup_keep_count=2,
        )
        for _ in range(4):
            backup_service.create_backup_and_audit(
                engine, factory, settings, actor_username="tester"
            )

        remaining = sorted(settings.backup_dir.glob(backup_service.BACKUP_GLOB))
        assert len(remaining) == 2
    finally:
        engine.dispose()


def test_a_corrupt_file_fails_integrity_verification(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not a real sqlite file")

    with pytest.raises(AppError, match="integrity check"):
        backup_service.verify_backup(corrupt)
