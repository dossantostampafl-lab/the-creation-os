"""Creator memory engine."""

import sqlalchemy as sa

from alembic import op

revision = "0016_memory_engine"
down_revision = "0015_rockmam_assessment"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "creator_memories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("creator_id", sa.String(36), sa.ForeignKey("creator.id"), nullable=False),
        sa.Column("memory_type", sa.String(32), nullable=False),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("normalized_content", sa.Text(), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("memory_fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "memory_type IN ('EPISODIC','SEMANTIC','OPERATIONAL','CREATOR')",
            name="ck_creator_memory_type",
        ),
        sa.CheckConstraint("importance BETWEEN 1 AND 10", name="ck_creator_memory_importance"),
        sa.CheckConstraint("char_length(memory_fingerprint) = 64", name="ck_creator_memory_fingerprint"),
    )
    op.create_index("ix_creator_memory_creator_type", "creator_memories", ["creator_id", "memory_type", "importance"])
    op.create_index("ix_creator_memory_created", "creator_memories", ["created_at", "id"])
    op.execute(
        """
        CREATE FUNCTION prevent_creator_memory_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'creator memory is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_creator_memory_immutable
        BEFORE UPDATE OR DELETE ON creator_memories
        FOR EACH ROW EXECUTE FUNCTION prevent_creator_memory_mutation()
        """
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_creator_memory_immutable ON creator_memories")
    op.drop_index("ix_creator_memory_created", table_name="creator_memories")
    op.drop_index("ix_creator_memory_creator_type", table_name="creator_memories")
    op.drop_table("creator_memories")
    op.execute("DROP FUNCTION IF EXISTS prevent_creator_memory_mutation()")
