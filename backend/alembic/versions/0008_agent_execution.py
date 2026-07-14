"""Controlled Agent task execution."""

import sqlalchemy as sa

from alembic import op

revision = "0008_agent_execution"
down_revision = "0007_agent_dispatcher_protocol"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dispatch_item_id", sa.String(36), sa.ForeignKey("dispatch_items.id"), nullable=False),
        sa.Column("mission_id", sa.String(36), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("worker_id", sa.String(36), sa.ForeignKey("workers.id"), nullable=False),
        sa.Column("capability_id", sa.String(36), sa.ForeignKey("capabilities.id"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("handler_name", sa.String(128), nullable=False),
        sa.Column("handler_version", sa.String(32), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("input_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("output_payload", sa.JSON()),
        sa.Column("result_metrics", sa.JSON()),
        sa.Column("result_warnings", sa.JSON()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("contract_json", sa.JSON(), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_duration_seconds", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "state IN ('pending','accepted','running','succeeded','failed','cancelled','timed_out')",
            name="ck_agent_execution_state",
        ),
        sa.CheckConstraint("attempt_number >= 0 AND max_duration_seconds > 0", name="ck_agent_execution_limits"),
        sa.UniqueConstraint("dispatch_item_id", "attempt_number", name="uq_execution_dispatch_attempt"),
    )
    op.create_index("ix_execution_mission_created", "agent_executions", ["mission_id", "created_at", "id"])
    op.create_index("ix_execution_worker_state", "agent_executions", ["worker_id", "state"])
    op.execute(
        "CREATE UNIQUE INDEX uq_execution_active_dispatch ON agent_executions (dispatch_item_id) "
        "WHERE state IN ('pending','accepted','running')"
    )
    op.create_table(
        "agent_execution_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("execution_id", sa.String(36), sa.ForeignKey("agent_executions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "event_type IN ('execution_created','execution_accepted','execution_started','execution_succeeded',"
            "'execution_failed','execution_cancelled','execution_timed_out','result_returned')",
            name="ck_execution_event_type",
        ),
        sa.UniqueConstraint("execution_id", "sequence", name="uq_execution_event_sequence"),
    )
    op.create_index("ix_execution_event_history", "agent_execution_events", ["execution_id", "sequence"])
    op.execute(
        "CREATE FUNCTION prevent_execution_event_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'agent execution events are append-only'; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER trg_execution_events_append_only BEFORE UPDATE OR DELETE ON agent_execution_events "
        "FOR EACH ROW EXECUTE FUNCTION prevent_execution_event_mutation()"
    )
    op.execute(
        "CREATE FUNCTION prevent_terminal_execution_mutation() RETURNS trigger AS $$ "
        "BEGIN IF OLD.state IN ('succeeded','failed','cancelled','timed_out') THEN "
        "RAISE EXCEPTION 'terminal agent execution is immutable'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER trg_terminal_execution_immutable BEFORE UPDATE ON agent_executions "
        "FOR EACH ROW EXECUTE FUNCTION prevent_terminal_execution_mutation()"
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_execution_events_append_only ON agent_execution_events")
    op.execute("DROP FUNCTION IF EXISTS prevent_execution_event_mutation()")
    op.execute("DROP TRIGGER IF EXISTS trg_terminal_execution_immutable ON agent_executions")
    op.execute("DROP FUNCTION IF EXISTS prevent_terminal_execution_mutation()")
    op.drop_index("ix_execution_event_history", table_name="agent_execution_events")
    op.drop_table("agent_execution_events")
    op.drop_index("uq_execution_active_dispatch", table_name="agent_executions")
    op.drop_index("ix_execution_worker_state", table_name="agent_executions")
    op.drop_index("ix_execution_mission_created", table_name="agent_executions")
    op.drop_table("agent_executions")
