"""remember camera sensor settings

Adds `cameras.sensor_settings_json`: the sensor configuration a camera SHOULD
be running with, so a worker can re-apply it whenever it (re)starts.

The ESP32 holds these in RAM only. A power blip therefore reverts the exposure
lock to automatic, an unlocked sensor hunts, the change gate reads that hunting
as motion, and inference goes from 11% of frames to nearly all of them - with
nothing anywhere reporting a problem. Persisting the intent is what closes it.

Revision ID: 0805d2807c0f
Revises: 3a287ff934d4
Create Date: 2026-08-12 10:06:42.647963
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import caps_dash.db.types  # noqa: F401  - registers UtcDateTime for autogenerate

revision: str = "0805d2807c0f"
down_revision: str | None = "3a287ff934d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `server_default` as well as a Python-side default: existing rows need a
    # value now, and NULL here would mean "no settings" in a column whose
    # empty state is an empty object.
    op.add_column(
        "cameras",
        sa.Column("sensor_settings_json", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("cameras", "sensor_settings_json")
