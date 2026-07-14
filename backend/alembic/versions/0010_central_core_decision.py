"""Central Core immutable Mission decision."""

import sqlalchemy as sa

from alembic import op

revision = "0010_central_core_decision"
down_revision = "0009_tree_core_consolidation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mission_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mission_id", sa.String(36), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("consolidation_id", sa.String(36), sa.ForeignKey("mission_consolidations.id"), nullable=True),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("justification_json", sa.JSON(), nullable=False),
        sa.Column("consolidation_fingerprint", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("mission_id", name="uq_mission_decision_mission"),
        sa.CheckConstraint(
            "decision IN ('APPROVED','REJECTED','REQUIRES_REVIEW')",
            name="ck_mission_decision_state",
        ),
        sa.CheckConstraint(
            "consolidation_fingerprint IS NULL OR char_length(consolidation_fingerprint) = 64",
            name="ck_mission_decision_fingerprint",
        ),
    )
    op.create_index("ix_mission_decision_created", "mission_decisions", ["created_at", "id"])
    op.execute(
        """
        CREATE FUNCTION prevent_mission_decision_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'mission decision is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_mission_decision_immutable
        BEFORE UPDATE OR DELETE ON mission_decisions
        FOR EACH ROW EXECUTE FUNCTION prevent_mission_decision_mutation()
        """
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_mission_decision_immutable ON mission_decisions")
    op.drop_index("ix_mission_decision_created", table_name="mission_decisions")
    op.drop_table("mission_decisions")
    op.execute("DROP FUNCTION IF EXISTS prevent_mission_decision_mutation()")
