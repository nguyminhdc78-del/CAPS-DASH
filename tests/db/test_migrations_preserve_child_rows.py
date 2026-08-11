"""A schema migration must not delete data.

This exists because one did. Adding a value to the `source_type` check
constraint needs a batch rebuild on SQLite - `CREATE TABLE tmp`, `INSERT
SELECT`, `DROP TABLE cameras`, `RENAME` - and with `PRAGMA foreign_keys=ON`
that DROP cascades through `parking_slots.camera_id ON DELETE CASCADE` and
`slot_state_history.slot_id ON DELETE CASCADE`. A migration that changed no
data wiped a live board's entire slot map and every state change ever
recorded for it.

The fix is in `migrations/env.py`, which disables foreign keys for the
duration. This test runs the real migration chain against a database with
real child rows and proves they are still there afterwards - so any future
migration that reintroduces the hazard fails here instead of on the board.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select

from caps_dash.db.enums import CameraSourceType
from caps_dash.db.models import Camera, ParkingSlot, SlotStateHistory
from caps_dash.db.session import create_session_factory, session_scope

REPO_ROOT = Path(__file__).resolve().parents[2]

SQUARE = [[10.0, 10.0], [110.0, 10.0], [110.0, 110.0], [10.0, 110.0]]


def _seed(database_url: str) -> None:
    """A camera with slots and history - the rows a cascade would take."""
    engine = create_engine(database_url)
    engine.dispose()

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    factory = create_session_factory(engine)

    with session_scope(factory) as session:
        camera = Camera(
            code="C1", source_type=CameraSourceType.ESP32CAM_HTTP, source_url="http://x/anh"
        )
        camera.slots = [
            ParkingSlot(code="A1", polygon_json=SQUARE, src_frame_width=640, src_frame_height=480),
            ParkingSlot(code="A2", polygon_json=SQUARE, src_frame_width=640, src_frame_height=480),
        ]
        session.add(camera)
        session.flush()
        session.add(
            SlotStateHistory(
                slot_id=camera.slots[0].id,
                camera_code="C1",
                slot_code="A1",
                floor="B1",
                new_state="OCCUPIED",
            )
        )
    engine.dispose()


def _counts(database_url: str) -> dict[str, int]:
    engine = create_engine(database_url)
    factory = create_session_factory(engine)
    with session_scope(factory) as session:
        counts = {
            "cameras": session.execute(select(func.count(Camera.id))).scalar_one(),
            "slots": session.execute(select(func.count(ParkingSlot.id))).scalar_one(),
            "history": session.execute(select(func.count(SlotStateHistory.id))).scalar_one(),
        }
    engine.dispose()
    return counts


@pytest.mark.integration
def test_upgrading_to_head_keeps_slots_and_history(tmp_path: Path):
    """Stamp an old revision, seed child rows, upgrade, and count."""
    database = tmp_path / "migrate.db"
    url = f"sqlite:///{database}"

    def alembic(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 - fixed argv, no shell, test-local paths
            [sys.executable, "-m", "alembic", "-x", f"url={url}", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )

    # Build the schema through Alembic at the revision BEFORE the batch
    # rebuild, rather than with `create_all` - `create_all` would produce the
    # current models' schema, and the upgrade under test would have nothing
    # left to change.
    initial = alembic("upgrade", "ed1dc6cf5238")
    assert initial.returncode == 0, initial.stderr

    _seed(url)
    before = _counts(url)
    assert before == {"cameras": 1, "slots": 2, "history": 1}

    upgraded = alembic("upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr

    after = _counts(url)
    assert after == before, (
        "the migration deleted child rows - a batch rebuild dropped the parent "
        "table with foreign keys enforced; see migrations/env.py"
    )
