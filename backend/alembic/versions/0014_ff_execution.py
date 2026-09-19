"""Reconcile kernel AgentExecution with durable worker execution.

Revision ID: 0014_ff_execution
Revises: 0013_ff_workers
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_ff_execution"
down_revision = "0013_ff_workers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0005_agent_executions already created the kernel attempt table. Keep
    # those columns and widen it with the durable dispatch/worker contract.
    op.alter_column("agent_executions", "attempt", existing_type=sa.Integer(), nullable=True)

    for column in (
        sa.Column("dispatch_item_id", sa.String(36), sa.ForeignKey("dispatch_items.id"), nullable=True),
        sa.Column("mission_id", sa.String(36), sa.ForeignKey("missions.id"), nullable=True),
        sa.Column("worker_id", sa.String(36), sa.ForeignKey("workers.id"), nullable=True),
        sa.Column("capability_id", sa.String(36), sa.ForeignKey("capabilities.id"), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=True),
        sa.Column("handler_name", sa.String(128), nullable=True),
        sa.Column("handler_version", sa.String(32), nullable=True),
        sa.Column("state", sa.String(32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("input_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("output_payload", sa.JSON(), nullable=True),
        sa.Column("result_metrics", sa.JSON(), nullable=True),
        sa.Column("result_warnings", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("contract_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    ):
        op.add_column("agent_executions", column)

    op.create_unique_constraint(
        "uq_execution_dispatch_attempt",
        "agent_executions",
        ["dispatch_item_id", "attempt_number"],
    )
    op.create_check_constraint(
        "ck_agent_execution_state",
        "agent_executions",
        "state IN ('pending','accepted','running','succeeded','failed','cancelled','timed_out')",
    )
    op.create_check_constraint(
        "ck_agent_execution_worker_limits",
        "agent_executions",
        "(attempt_number IS NULL OR attempt_number >= 0) AND "
        "(max_duration_seconds IS NULL OR max_duration_seconds > 0)",
    )
    op.create_index("ix_execution_mission_created", "agent_executions", ["mission_id", "created_at", "id"])
    op.create_index("ix_execution_worker_state", "agent_executions", ["worker_id", "state"])
    op.execute(
        "CREATE UNIQUE INDEX uq_execution_active_dispatch ON agent_executions (dispatch_item_id) "
        "WHERE dispatch_item_id IS NOT NULL AND state IN ('pending','accepted','running')"
    )

    op.create_table(
        "agent_execution_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "execution_id",
            sa.String(36),
            sa.ForeignKey("agent_executions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "event_type IN ('execution_created','execution_reclaimed','execution_accepted',"
            "'execution_started','execution_succeeded','execution_failed','execution_cancelled',"
            "'execution_timed_out','result_returned')",
            name="ck_execution_event_type",
        ),
        sa.UniqueConstraint("execution_id", "sequence", name="uq_execution_event_sequence"),
    )
    op.create_index(
        "ix_execution_event_history",
        "agent_execution_events",
        ["execution_id", "sequence"],
    )
    op.execute(
        "CREATE OR REPLACE FUNCTION prevent_execution_event_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'agent execution events are append-only'; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER trg_execution_events_append_only BEFORE UPDATE OR DELETE ON agent_execution_events "
        "FOR EACH ROW EXECUTE FUNCTION prevent_execution_event_mutation()"
    )
    op.execute(
        "CREATE OR REPLACE FUNCTION prevent_terminal_execution_mutation() RETURNS trigger AS $$ "
        "BEGIN IF OLD.state IN ('succeeded','failed','cancelled','timed_out') THEN "
        "RAISE EXCEPTION 'terminal agent execution is immutable'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER trg_terminal_execution_immutable BEFORE UPDATE ON agent_executions "
        "FOR EACH ROW EXECUTE FUNCTION prevent_terminal_execution_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_execution_events_append_only ON agent_execution_events")
    op.execute("DROP FUNCTION IF EXISTS prevent_execution_event_mutation()")
    op.execute("DROP TRIGGER IF EXISTS trg_terminal_execution_immutable ON agent_executions")
    op.execute("DROP FUNCTION IF EXISTS prevent_terminal_execution_mutation()")
    op.drop_index("ix_execution_event_history", table_name="agent_execution_events")
    op.drop_table("agent_execution_events")
    op.drop_index("uq_execution_active_dispatch", table_name="agent_executions")
    op.drop_index("ix_execution_worker_state", table_name="agent_executions")
    op.drop_index("ix_execution_mission_created", table_name="agent_executions")
    op.drop_constraint("ck_agent_execution_worker_limits", "agent_executions", type_="check")
    op.drop_constraint("ck_agent_execution_state", "agent_executions", type_="check")
    op.drop_constraint("uq_execution_dispatch_attempt", "agent_executions", type_="unique")
    for name in (
        "version","updated_at","created_at","finished_at","max_duration_seconds","deadline",
        "contract_json","error_message","error_code","result_warnings","result_metrics",
        "output_payload","input_payload","state","handler_version","handler_name",
        "attempt_number","capability_id","worker_id","mission_id","dispatch_item_id",
    ):
        op.drop_column("agent_executions", name)
    op.alter_column("agent_executions", "attempt", existing_type=sa.Integer(), nullable=False)
