"""DEUS conversation orchestration."""

import sqlalchemy as sa

from alembic import op

revision = "0019_ff_god"
down_revision = "0018_ff_malkuth"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "god_conversation_interactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("creator_message_id", sa.String(36), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("god_message_id", sa.String(36), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("interaction_type", sa.String(32), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=False),
        sa.Column("potential_detected", sa.Boolean(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("conversation_id", "idempotency_key", name="uq_god_interaction_conversation_idempotency"),
        sa.CheckConstraint(
            "interaction_type IN ('DIRECT_RESPONSE','INFORMATIONAL','POTENTIAL','UNSUPPORTED')",
            name="ck_god_interaction_type",
        ),
        sa.CheckConstraint("char_length(fingerprint) = 64", name="ck_god_interaction_fingerprint"),
    )
    op.create_index("ix_god_interaction_created", "god_conversation_interactions", ["created_at", "id"])
    op.execute(
        """
        CREATE FUNCTION prevent_god_conversation_interaction_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'DEUS conversation interaction is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_god_conversation_interaction_immutable
        BEFORE UPDATE OR DELETE ON god_conversation_interactions
        FOR EACH ROW EXECUTE FUNCTION prevent_god_conversation_interaction_mutation()
        """
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_god_conversation_interaction_immutable ON god_conversation_interactions")
    op.drop_index("ix_god_interaction_created", table_name="god_conversation_interactions")
    op.drop_table("god_conversation_interactions")
    op.execute("DROP FUNCTION IF EXISTS prevent_god_conversation_interaction_mutation()")
