"""Central Core policy reasoning."""

import sqlalchemy as sa

from alembic import op

revision = "0011_policy_reasoning"
down_revision = "0010_central_core_decision"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mission_decision_reasoning",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("decision_id", sa.String(36), sa.ForeignKey("mission_decisions.id"), nullable=False),
        sa.Column("policy_version", sa.String(32), nullable=False),
        sa.Column("evaluation_timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("rules_applied", sa.JSON(), nullable=False),
        sa.Column("consistency_summary", sa.JSON(), nullable=False),
        sa.Column("completeness_summary", sa.JSON(), nullable=False),
        sa.Column("explanation_payload", sa.JSON(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("decision_id", name="uq_mission_decision_reasoning_decision"),
        sa.CheckConstraint("char_length(fingerprint) = 64", name="ck_mission_decision_reasoning_fingerprint"),
    )
    op.create_index("ix_mission_decision_reasoning_created", "mission_decision_reasoning", ["created_at", "id"])
    op.execute(
        """
        CREATE FUNCTION prevent_mission_decision_reasoning_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'mission decision reasoning is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_mission_decision_reasoning_immutable
        BEFORE UPDATE OR DELETE ON mission_decision_reasoning
        FOR EACH ROW EXECUTE FUNCTION prevent_mission_decision_reasoning_mutation()
        """
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_mission_decision_reasoning_immutable ON mission_decision_reasoning")
    op.drop_index("ix_mission_decision_reasoning_created", table_name="mission_decision_reasoning")
    op.drop_table("mission_decision_reasoning")
    op.execute("DROP FUNCTION IF EXISTS prevent_mission_decision_reasoning_mutation()")
