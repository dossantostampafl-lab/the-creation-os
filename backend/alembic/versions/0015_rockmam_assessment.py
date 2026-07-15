"""ROCKMAM possibility assessment."""

import sqlalchemy as sa

from alembic import op

revision = "0015_rockmam_assessment"
down_revision = "0014_sophia_understanding"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rockmam_possibility_assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("sophia_understanding_id", sa.String(36), sa.ForeignKey("sophia_understandings.id"), nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("assessment_result", sa.String(32), nullable=False),
        sa.Column("assessment_payload", sa.JSON(), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("assessment_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("sophia_understanding_id", name="uq_rockmam_assessment_sophia_understanding"),
        sa.CheckConstraint(
            "assessment_result IN ('VIABLE','NOT_VIABLE','REQUIRES_CREATOR')",
            name="ck_rockmam_assessment_result",
        ),
        sa.CheckConstraint("char_length(source_fingerprint) = 64", name="ck_rockmam_source_fingerprint"),
        sa.CheckConstraint("char_length(assessment_fingerprint) = 64", name="ck_rockmam_assessment_fingerprint"),
    )
    op.create_index("ix_rockmam_assessment_created", "rockmam_possibility_assessments", ["created_at", "id"])
    op.execute(
        """
        CREATE FUNCTION prevent_rockmam_assessment_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'rockmam assessment is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_rockmam_assessment_immutable
        BEFORE UPDATE OR DELETE ON rockmam_possibility_assessments
        FOR EACH ROW EXECUTE FUNCTION prevent_rockmam_assessment_mutation()
        """
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_rockmam_assessment_immutable ON rockmam_possibility_assessments")
    op.drop_index("ix_rockmam_assessment_created", table_name="rockmam_possibility_assessments")
    op.drop_table("rockmam_possibility_assessments")
    op.execute("DROP FUNCTION IF EXISTS prevent_rockmam_assessment_mutation()")
