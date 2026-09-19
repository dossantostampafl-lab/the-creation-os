"""Tree Core Mission consolidation."""

import sqlalchemy as sa

from alembic import op

revision = "0015_ff_consolidate"
down_revision = "0014_ff_execution"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mission_consolidations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mission_id", sa.String(36), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("inconsistencies_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("completeness_json", sa.JSON(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("mission_id", name="uq_mission_consolidation_mission"),
        sa.CheckConstraint("status IN ('complete')", name="ck_mission_consolidation_status"),
        sa.CheckConstraint("char_length(fingerprint) = 64", name="ck_mission_consolidation_fingerprint"),
    )
    op.create_index(
        "ix_mission_consolidation_created",
        "mission_consolidations",
        ["created_at", "id"],
    )


def downgrade():
    op.drop_index("ix_mission_consolidation_created", table_name="mission_consolidations")
    op.drop_table("mission_consolidations")
