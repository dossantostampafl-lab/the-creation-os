"""Canonical diagnostic incidents and separate cause hypotheses."""

import sqlalchemy as sa
from alembic import op

revision = "0014_diagnostic_incidents"
down_revision = "0013_service_heartbeats"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "diagnostic_incidents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("creator_id", sa.String(36), sa.ForeignKey("creator.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("resource", sa.String(128), nullable=False),
        sa.Column("rule", sa.String(128), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observation_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("creator_id", "fingerprint", name="uq_diagnostic_incident_fingerprint"),
    )
    op.create_index("ix_diagnostic_incidents_creator_id", "diagnostic_incidents", ["creator_id"])
    op.create_table(
        "diagnostic_cause_hypotheses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("creator_id", sa.String(36), sa.ForeignKey("creator.id", ondelete="CASCADE"), nullable=False),
        sa.Column("incident_id", sa.String(36), sa.ForeignKey("diagnostic_incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_type", sa.String(64), nullable=False),
        sa.Column("author_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'hypothesis'")),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_diagnostic_cause_hypotheses_creator_id", "diagnostic_cause_hypotheses", ["creator_id"])
    op.create_index("ix_diagnostic_cause_hypotheses_incident_id", "diagnostic_cause_hypotheses", ["incident_id"])


def downgrade():
    op.drop_table("diagnostic_cause_hypotheses")
    op.drop_table("diagnostic_incidents")
