"""Persist AgentExecution attempts.

Revision ID: 0005_agent_executions
Revises: 0004_kernel_invariants
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005_agent_executions"
down_revision = "0004_kernel_invariants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'RUNNING'")),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("input_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("output_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("task_id", "attempt", name="uq_agent_executions_task_attempt"),
        sa.CheckConstraint("attempt > 0", name="ck_agent_execution_attempt_positive"),
        sa.CheckConstraint(
            "status IN ('RUNNING','SUCCEEDED','FAILED','CANCELLED')",
            name="ck_agent_execution_status",
        ),
    )
    op.create_index("ix_agent_executions_task_id", "agent_executions", ["task_id"])
    op.create_index("ix_agent_executions_agent_id", "agent_executions", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_executions_agent_id", table_name="agent_executions")
    op.drop_index("ix_agent_executions_task_id", table_name="agent_executions")
    op.drop_table("agent_executions")
