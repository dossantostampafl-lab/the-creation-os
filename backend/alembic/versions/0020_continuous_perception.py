"""continuous perception

Revision ID: 0020_continuous_perception
Revises: 0019_opportunity_discovery
Create Date: 2026-07-16 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_continuous_perception"
down_revision: str | None = "0019_opportunity_discovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("opportunity_observations", sa.Column("external_id", sa.String(length=256), nullable=True))
    op.create_index("ix_opportunity_observations_source_external_id", "opportunity_observations", ["source", "external_id"])

    op.create_table(
        "perception_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("universe", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("capability_name", sa.String(length=128), nullable=False),
        sa.Column("connector_name", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("schedule_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("minimum_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("config_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("secret_env_var", sa.String(length=128), nullable=True),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_succeeded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_cursor", sa.String(length=512), nullable=True),
        sa.Column("last_etag", sa.String(length=256), nullable=True),
        sa.Column("last_modified", sa.String(length=256), nullable=True),
        sa.Column("failure_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_perception_sources_name"),
    )
    op.create_index("ix_perception_sources_enabled_next_run", "perception_sources", ["enabled", "next_run_at"])

    op.create_table(
        "perception_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("observations_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("opportunities_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("attempts_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["perception_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_perception_runs_source_started", "perception_runs", ["source_id", "started_at"])

    op.create_table(
        "creator_notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recipient_actor_id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("opportunity_id", sa.String(length=36), nullable=True),
        sa.Column("priority_score", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_creator_notifications_recipient_status", "creator_notifications", ["recipient_actor_id", "status"])
    op.create_index("ix_creator_notifications_opportunity", "creator_notifications", ["opportunity_id"])


def downgrade() -> None:
    op.drop_index("ix_creator_notifications_opportunity", table_name="creator_notifications")
    op.drop_index("ix_creator_notifications_recipient_status", table_name="creator_notifications")
    op.drop_table("creator_notifications")
    op.drop_index("ix_perception_runs_source_started", table_name="perception_runs")
    op.drop_table("perception_runs")
    op.drop_index("ix_perception_sources_enabled_next_run", table_name="perception_sources")
    op.drop_table("perception_sources")
    op.drop_index("ix_opportunity_observations_source_external_id", table_name="opportunity_observations")
    op.drop_column("opportunity_observations", "external_id")
