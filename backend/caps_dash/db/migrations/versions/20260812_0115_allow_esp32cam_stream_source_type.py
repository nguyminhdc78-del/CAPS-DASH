"""allow esp32cam_stream source type

Adds `esp32cam_stream` to the `source_type_valid` check constraint.

SQLite cannot alter a CHECK constraint, so `batch_alter_table` rebuilds the
table: create a copy with the new constraint, move the rows, swap. That is why
`render_as_batch=True` is set in `env.py` - without it this migration silently
does nothing on SQLite and the new source type is rejected at insert time.

Revision ID: 3a287ff934d4
Revises: ed1dc6cf5238
Create Date: 2026-08-12 01:15:51.769425
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

import caps_dash.db.types  # noqa: F401  - registers UtcDateTime for autogenerate

revision: str = "3a287ff934d4"
down_revision: str | None = "ed1dc6cf5238"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT_NAME = "source_type_valid"

OLD_VALUES = ("esp32cam_http", "image_folder", "video_file", "fake")
NEW_VALUES = ("esp32cam_http", "esp32cam_stream", "image_folder", "video_file", "fake")


def _condition(values: Sequence[str]) -> str:
    return "source_type IN ({})".format(", ".join(f"'{value}'" for value in values))


def upgrade() -> None:
    with op.batch_alter_table("cameras") as batch:
        batch.drop_constraint(CONSTRAINT_NAME, type_="check")
        batch.create_check_constraint(CONSTRAINT_NAME, _condition(NEW_VALUES))


def downgrade() -> None:
    # Any camera already using the new source type would violate the restored
    # constraint, so move it back to the polling source rather than failing
    # the migration halfway through a rebuild.
    op.execute(
        "UPDATE cameras SET source_type = 'esp32cam_http' "
        "WHERE source_type = 'esp32cam_stream'"
    )
    with op.batch_alter_table("cameras") as batch:
        batch.drop_constraint(CONSTRAINT_NAME, type_="check")
        batch.create_check_constraint(CONSTRAINT_NAME, _condition(OLD_VALUES))
