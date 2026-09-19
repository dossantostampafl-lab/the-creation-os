"""mission authorization scope

Revision ID: 0027_ff_mission_auth
Revises: 0026_ff_perception
Create Date: 2026-07-16 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "0027_ff_mission_auth"
down_revision = "0026_ff_perception"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mission_authorizations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("mission_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=256), nullable=False),
        sa.Column("creator_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("scope_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("allowed_capabilities_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("allowed_resources_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("restrictions_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("metadata_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("denial_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["creator_id"], ["creator.id"]),
        sa.ForeignKeyConstraint(["mission_id"], ["missions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('pending','authorized','suspended','revoked','completed')", name="ck_mission_authorization_status"),
    )
    op.create_index("ix_mission_authorizations_mission_status", "mission_authorizations", ["mission_id", "status"])
    op.create_index(
        "uq_mission_authorizations_active_mission",
        "mission_authorizations",
        ["mission_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending','authorized','suspended')"),
    )


def downgrade() -> None:
    op.drop_index("uq_mission_authorizations_active_mission", table_name="mission_authorizations")
    op.drop_index("ix_mission_authorizations_mission_status", table_name="mission_authorizations")
    op.drop_table("mission_authorizations")
