"""Persist capability invocation decisions and results.

Revision ID: 0006_capability_invocations
Revises: 0005_agent_executions
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006_capability_invocations"
down_revision = "0005_agent_executions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capability_invocations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mission_id", sa.String(36), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("agent_execution_id", sa.String(36), sa.ForeignKey("agent_executions.id"), nullable=True),
        sa.Column("capability", sa.String(128), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("external_effect", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("idempotency_class", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(256), nullable=True),
        sa.Column("authorization_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("result_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('AUTHORIZED','DENIED','SUCCEEDED','FAILED','UNCERTAIN')",
            name="ck_capability_invocation_status",
        ),
        sa.CheckConstraint("authorization_version > 0", name="ck_capability_authorization_version_positive"),
    )
    op.create_index("ix_capability_invocations_mission_id", "capability_invocations", ["mission_id"])
    op.create_index("ix_capability_invocations_task_id", "capability_invocations", ["task_id"])
    op.create_index("ix_capability_invocations_agent_execution_id", "capability_invocations", ["agent_execution_id"])
    op.create_index(
        "uq_capability_at_most_once_key",
        "capability_invocations",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_capability_at_most_once_key", table_name="capability_invocations")
    op.drop_index("ix_capability_invocations_agent_execution_id", table_name="capability_invocations")
    op.drop_index("ix_capability_invocations_task_id", table_name="capability_invocations")
    op.drop_index("ix_capability_invocations_mission_id", table_name="capability_invocations")
    op.drop_table("capability_invocations")
