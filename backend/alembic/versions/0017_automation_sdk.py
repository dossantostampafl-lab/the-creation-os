"""Automation SDK foundation."""

import sqlalchemy as sa

from alembic import op

revision = "0017_automation_sdk"
down_revision = "0016_memory_engine"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "automation_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("creator_id", sa.String(36), sa.ForeignKey("creator.id"), nullable=False),
        sa.Column("connector_id", sa.String(128), nullable=False),
        sa.Column("capability", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("error_message", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("creator_id", "connector_id", "idempotency_key", name="uq_automation_execution_idempotency"),
        sa.CheckConstraint(
            "status IN ('SUCCEEDED','FAILED','TIMEOUT','REJECTED')",
            name="ck_automation_execution_status",
        ),
        sa.CheckConstraint("char_length(request_fingerprint) = 64", name="ck_automation_execution_fingerprint"),
    )
    op.create_index("ix_automation_execution_creator_created", "automation_executions", ["creator_id", "created_at", "id"])
    op.create_index("ix_automation_execution_connector", "automation_executions", ["connector_id", "capability", "status"])
    op.execute(
        """
        CREATE FUNCTION prevent_automation_execution_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'automation execution is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_automation_execution_immutable
        BEFORE UPDATE OR DELETE ON automation_executions
        FOR EACH ROW EXECUTE FUNCTION prevent_automation_execution_mutation()
        """
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_automation_execution_immutable ON automation_executions")
    op.drop_index("ix_automation_execution_connector", table_name="automation_executions")
    op.drop_index("ix_automation_execution_creator_created", table_name="automation_executions")
    op.drop_table("automation_executions")
    op.execute("DROP FUNCTION IF EXISTS prevent_automation_execution_mutation()")
