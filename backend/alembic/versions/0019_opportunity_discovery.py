"""Opportunity discovery persistence."""

import sqlalchemy as sa

from alembic import op

revision = "0019_opportunity_discovery"
down_revision = "0018_capability_persistence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "opportunity_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("universe", sa.String(64), nullable=False),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("subject", sa.String(256), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("normalized_data", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("source_reliability", sa.Float(), nullable=False),
        sa.Column("correlation_key", sa.String(256), nullable=False),
        sa.Column("observation_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("observation_fingerprint", name="uq_opportunity_observation_fingerprint"),
        sa.CheckConstraint("source_reliability >= 0 and source_reliability <= 1", name="ck_opportunity_observation_reliability"),
    )
    op.create_index("ix_opportunity_observations_correlation", "opportunity_observations", ["correlation_key"])
    op.create_index("ix_opportunity_observations_universe", "opportunity_observations", ["universe"])

    op.create_table(
        "opportunities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("universe", sa.String(64), nullable=False),
        sa.Column("category", sa.String(128), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("impact", sa.Float(), nullable=False),
        sa.Column("urgency", sa.Float(), nullable=False),
        sa.Column("risk", sa.Float(), nullable=False),
        sa.Column("source_reliability", sa.Float(), nullable=False),
        sa.Column("priority_score", sa.Float(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("risks", sa.JSON(), nullable=False),
        sa.Column("scoring", sa.JSON(), nullable=False),
        sa.Column("correlation_key", sa.String(256), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(36), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("inception_id", sa.String(36), sa.ForeignKey("inceptions.id"), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_opportunity_confidence"),
        sa.CheckConstraint("impact >= 0 and impact <= 1", name="ck_opportunity_impact"),
        sa.CheckConstraint("urgency >= 0 and urgency <= 1", name="ck_opportunity_urgency"),
        sa.CheckConstraint("risk >= 0 and risk <= 1", name="ck_opportunity_risk"),
        sa.CheckConstraint("priority_score >= 0 and priority_score <= 1", name="ck_opportunity_priority"),
    )
    op.create_index("ix_opportunities_ranking", "opportunities", ["priority_score", "detected_at"])
    op.create_index("ix_opportunities_status", "opportunities", ["status"])
    op.create_index("ix_opportunities_universe", "opportunities", ["universe"])

    op.create_table(
        "opportunity_evidence",
        sa.Column("opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("observation_id", sa.String(36), sa.ForeignKey("opportunity_observations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade():
    op.drop_table("opportunity_evidence")
    op.drop_index("ix_opportunities_universe", table_name="opportunities")
    op.drop_index("ix_opportunities_status", table_name="opportunities")
    op.drop_index("ix_opportunities_ranking", table_name="opportunities")
    op.drop_table("opportunities")
    op.drop_index("ix_opportunity_observations_universe", table_name="opportunity_observations")
    op.drop_index("ix_opportunity_observations_correlation", table_name="opportunity_observations")
    op.drop_table("opportunity_observations")
