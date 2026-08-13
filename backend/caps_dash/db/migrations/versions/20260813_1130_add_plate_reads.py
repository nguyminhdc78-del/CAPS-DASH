"""Plates read when a slot fills.

A guard's question is "where is 30H-832.31?", so the table is indexed for
plate-then-time. It is also indexed slot-then-time, which serves both "what is
in this bay?" and the retention purge that sweeps by age.

Revision ID: 8b3f2c1a9e47
Revises: 7c4e1b9a2f38
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8b3f2c1a9e47"
down_revision: str | None = "7c4e1b9a2f38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plate_reads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slot_id", sa.Integer(), nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        # Normalised to letters and digits: `30H-832.31` is stored `30H83231`,
        # so a search does not depend on how the guard typed the punctuation.
        sa.Column("plate", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("plate_width_px", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("read_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("plate <> ''", name="plate_not_empty"),
        sa.CheckConstraint("plate_width_px > 0", name="plate_width_positive"),
        sa.ForeignKeyConstraint(["slot_id"], ["parking_slots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plate_reads_slot_id", "plate_reads", ["slot_id"])
    op.create_index("ix_plate_reads_camera_id", "plate_reads", ["camera_id"])
    op.create_index("ix_plate_reads_plate", "plate_reads", ["plate"])
    op.create_index("ix_plate_reads_read_at", "plate_reads", ["read_at"])
    op.create_index("ix_plate_reads_plate_time", "plate_reads", ["plate", "read_at"])
    op.create_index("ix_plate_reads_slot_time", "plate_reads", ["slot_id", "read_at"])


def downgrade() -> None:
    op.drop_table("plate_reads")
