"""Persist projection checkpoints.

Revision ID: 0007_projection_checkpoints
Revises: 0006_capability_invocations
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007_projection_checkpoints"
down_revision = "0006_capability_invocations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projection_checkpoints",
        sa.Column("projection_name", sa.String(length=128), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("state_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_check_constraint(
        "ck_projection_checkpoint_position_nonnegative",
        "projection_checkpoints",
        "position >= 0",
    )


def downgrade() -> None:
    op.drop_table("projection_checkpoints")
