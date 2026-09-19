"""SOPHIA deterministic understanding."""

import sqlalchemy as sa

from alembic import op

revision = "0020_ff_sophia"
down_revision = "0019_ff_god"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sophia_understandings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("god_interaction_id", sa.String(36), sa.ForeignKey("god_conversation_interactions.id"), nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("understanding_type", sa.String(40), nullable=False),
        sa.Column("understanding_payload", sa.JSON(), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("understanding_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("understood_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("god_interaction_id", name="uq_sophia_understanding_god_interaction"),
        sa.CheckConstraint(
            (
                "understanding_type IN ("
                "'DIRECT_UNDERSTANDING','INFORMATIONAL_UNDERSTANDING',"
                "'POTENTIAL_UNDERSTANDING','UNSUPPORTED_UNDERSTANDING')"
            ),
            name="ck_sophia_understanding_type",
        ),
        sa.CheckConstraint("char_length(source_fingerprint) = 64", name="ck_sophia_source_fingerprint"),
        sa.CheckConstraint("char_length(understanding_fingerprint) = 64", name="ck_sophia_understanding_fingerprint"),
    )
    op.create_index("ix_sophia_understanding_created", "sophia_understandings", ["created_at", "id"])
    op.execute(
        """
        CREATE FUNCTION prevent_sophia_understanding_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'sophia understanding is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_sophia_understanding_immutable
        BEFORE UPDATE OR DELETE ON sophia_understandings
        FOR EACH ROW EXECUTE FUNCTION prevent_sophia_understanding_mutation()
        """
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_sophia_understanding_immutable ON sophia_understandings")
    op.drop_index("ix_sophia_understanding_created", table_name="sophia_understandings")
    op.drop_table("sophia_understandings")
    op.execute("DROP FUNCTION IF EXISTS prevent_sophia_understanding_mutation()")
