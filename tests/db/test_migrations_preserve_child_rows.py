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

import json
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

REPO_ROOT = Path(__file__).resolve().parents[2]

SQUARE = [[10.0, 10.0], [110.0, 10.0], [110.0, 110.0], [10.0, 110.0]]


def _seed(database_url: str) -> None:
    """A camera with slots and history - the rows a cascade would take.

    Raw SQL, naming only the columns that exist at the revision under test.
    Using the ORM here would couple this test to whatever the models look like
    today: the models always run ahead of the schema, so the first migration
    to add a column would break the seed rather than the thing being tested.
    """
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql(
            "INSERT INTO cameras (id, code, name, floor, source_type, source_url,"
            " poll_interval_s, vote_window, vote_threshold, confidence, is_enabled,"
            " frame_width, frame_height, last_error, created_at, updated_at)"
            " VALUES (1, 'C1', '', 'B1', 'esp32cam_http', 'http://x/anh',"
            " 3.0, 5, 4, 0.25, 1, 0, 0, '', '2026-01-01', '2026-01-01')"
        )
        for slot_id, code in ((1, "A1"), (2, "A2")):
            connection.exec_driver_sql(
                "INSERT INTO parking_slots (id, camera_id, code, floor, polygon_json,"
                " src_frame_width, src_frame_height, current_state, is_active,"
                " created_at, updated_at)"
                " VALUES (?, 1, ?, 'B1', ?, 640, 480, 'UNKNOWN', 1,"
                " '2026-01-01', '2026-01-01')",
                (slot_id, code, json.dumps(SQUARE)),
            )
        connection.exec_driver_sql(
            "INSERT INTO slot_state_history (id, slot_id, camera_code, slot_code,"
            " floor, previous_state, new_state, changed_at, clock_suspect)"
            " VALUES (1, 1, 'C1', 'A1', 'B1', 'UNKNOWN', 'OCCUPIED',"
            " '2026-01-01', 0)"
        )
    engine.dispose()


def _counts(database_url: str) -> dict[str, int]:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        counts = {
            table: connection.exec_driver_sql(
                f"SELECT count(*) FROM {table}"  # noqa: S608 - fixed table names
            ).scalar_one()
            for table in ("cameras", "parking_slots", "slot_state_history")
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
    assert before == {"cameras": 1, "parking_slots": 2, "slot_state_history": 1}

    upgraded = alembic("upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr

    after = _counts(url)
    assert after == before, (
        "the migration deleted child rows - a batch rebuild dropped the parent "
        "table with foreign keys enforced; see migrations/env.py"
    )
