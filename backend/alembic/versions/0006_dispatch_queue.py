"""Dispatch Queue Foundation."""

import sqlalchemy as sa

from alembic import op

revision = "0006_dispatch_queue"
down_revision = "0005_mission_planner"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dispatch_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("mission_id", sa.String(36), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("agents.id")),
        sa.Column("capability_id", sa.String(36), sa.ForeignKey("capabilities.id")),
        sa.Column("state", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_token_hash", sa.String(64)),
        sa.Column("leased_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_error_code", sa.String(64)),
        sa.Column("last_error_message", sa.Text()),
        sa.Column("last_failed_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "state IN ('queued','leased','acknowledged','retry_scheduled','failed','dead_lettered','cancelled')", name="ck_dispatch_state"
        ),
        sa.CheckConstraint("attempt_count >= 0 AND max_attempts > 0", name="ck_dispatch_attempts"),
    )
    op.create_index("ix_dispatch_lease_order", "dispatch_items", [sa.text("priority DESC"), "available_at", "created_at", "id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_dispatch_active_task ON dispatch_items (task_id) WHERE state IN ('queued','leased','retry_scheduled')"
    )
    op.create_table(
        "dispatch_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dispatch_item_id", sa.String(36), sa.ForeignKey("dispatch_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("worker_id", sa.String(128)),
        sa.Column("lease_token_hash", sa.String(64)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_dispatch_attempt_history", "dispatch_attempts", ["dispatch_item_id", "attempt_number", "created_at"])


def downgrade():
    op.drop_table("dispatch_attempts")
    op.drop_index("uq_dispatch_active_task", table_name="dispatch_items")
    op.drop_index("ix_dispatch_lease_order", table_name="dispatch_items")
    op.drop_table("dispatch_items")
