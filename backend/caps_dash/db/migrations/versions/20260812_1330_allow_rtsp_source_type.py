"""allow rtsp source type

Adds `rtsp` to the `source_type_valid` check constraint, so any RTSP camera -
IP camera, action camera, NVR sub-stream - can be registered alongside the
ESP32-CAM sources.

SQLite cannot alter a CHECK constraint, so `batch_alter_table` rebuilds the
table: create a copy with the new constraint, move the rows, swap. That is why
`render_as_batch=True` is set in `env.py` - without it this migration silently
does nothing on SQLite and the new source type is rejected at insert time.

The rebuild is also why `env.py` turns `PRAGMA foreign_keys` OFF around the
migration run: with it on, dropping the original `cameras` table cascades to
every `parking_slots` row that references it, and the slot map is gone.

Revision ID: 7c4e1b9a2f38
Revises: 0805d2807c0f
Create Date: 2026-08-12 13:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

import caps_dash.db.types  # noqa: F401  - registers UtcDateTime for autogenerate

revision: str = "7c4e1b9a2f38"
down_revision: str | None = "0805d2807c0f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT_NAME = "source_type_valid"

OLD_VALUES = ("esp32cam_http", "esp32cam_stream", "image_folder", "video_file", "fake")
NEW_VALUES = (
    "esp32cam_http",
    "esp32cam_stream",
    "rtsp",
    "image_folder",
    "video_file",
    "fake",
)


def _condition(values: Sequence[str]) -> str:
    return "source_type IN ({})".format(", ".join(f"'{value}'" for value in values))


def upgrade() -> None:
    with op.batch_alter_table("cameras") as batch:
        batch.drop_constraint(CONSTRAINT_NAME, type_="check")
        batch.create_check_constraint(CONSTRAINT_NAME, _condition(NEW_VALUES))


def downgrade() -> None:
    # An RTSP camera would violate the restored constraint. Disable it rather
    # than rewrite its source_type: pointing an RTSP URL at the ESP32-CAM
    # poller would leave a camera that looks configured and can never work,
    # whereas a disabled row is obvious and its slot map survives.
    op.execute("UPDATE cameras SET is_enabled = 0 WHERE source_type = 'rtsp'")
    op.execute("UPDATE cameras SET source_type = 'fake' WHERE source_type = 'rtsp'")
    with op.batch_alter_table("cameras") as batch:
        batch.drop_constraint(CONSTRAINT_NAME, type_="check")
        batch.create_check_constraint(CONSTRAINT_NAME, _condition(OLD_VALUES))
