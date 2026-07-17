"""Malkuth mission manifestation."""

import sqlalchemy as sa

from alembic import op

revision = "0012_malkuth_manifestation"
down_revision = "0011_policy_reasoning"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mission_manifestations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mission_id", sa.String(36), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("decision_id", sa.String(36), sa.ForeignKey("mission_decisions.id"), nullable=False),
        sa.Column("manifestation_state", sa.String(32), nullable=False),
        sa.Column("manifestation_payload", sa.JSON(), nullable=False),
        sa.Column("manifestation_fingerprint", sa.String(64), nullable=False),
        sa.Column("audit_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("manifested_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
        sa.UniqueConstraint("mission_id", name="uq_mission_manifestation_mission"),
        sa.UniqueConstraint("decision_id", name="uq_mission_manifestation_decision"),
        sa.CheckConstraint(
            "manifestation_state IN ('PENDING','MANIFESTED','FAILED')",
            name="ck_mission_manifestation_state",
        ),
        sa.CheckConstraint("char_length(manifestation_fingerprint) = 64", name="ck_mission_manifestation_fingerprint"),
    )
    op.create_index("ix_mission_manifestation_created", "mission_manifestations", ["created_at", "id"])
    op.execute(
        """
        CREATE FUNCTION prevent_mission_manifestation_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'mission manifestation is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_mission_manifestation_immutable
        BEFORE UPDATE OR DELETE ON mission_manifestations
        FOR EACH ROW EXECUTE FUNCTION prevent_mission_manifestation_mutation()
        """
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_mission_manifestation_immutable ON mission_manifestations")
    op.drop_index("ix_mission_manifestation_created", table_name="mission_manifestations")
    op.drop_table("mission_manifestations")
    op.execute("DROP FUNCTION IF EXISTS prevent_mission_manifestation_mutation()")
