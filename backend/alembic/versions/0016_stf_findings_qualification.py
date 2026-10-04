"""Persist verified STF findings and evidence-based qualification results.

Revision ID: 0016_stf_findings_qualification
Revises: 0015_stf_evidence
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0016_stf_findings_qualification"
down_revision = "0015_stf_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stf_findings",
        sa.Column("finding_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("mission_id", sa.String(128), nullable=False),
        sa.Column("action_id", sa.String(128), nullable=False),
        sa.Column("task_id", sa.String(128), nullable=False),
        sa.Column("environment_id", sa.String(128), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("attack_evidence", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("defense_evidence", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("reproduced", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["stf_runs.id"]),
        sa.PrimaryKeyConstraint("finding_id"),
        sa.UniqueConstraint("run_id", "action_id", "finding_id", name="uq_stf_finding_projection"),
        sa.CheckConstraint("status IN ('confirmed')", name="ck_stf_finding_status"),
    )
    op.create_index("ix_stf_findings_run_id", "stf_findings", ["run_id"])
    op.create_index("ix_stf_findings_action_id", "stf_findings", ["action_id"])

    op.create_table(
        "stf_qualifications",
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        sa.Column("level", sa.String(16), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("failed_gates", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("passed_gates", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("reasons", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["stf_runs.id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )

    op.execute(
        """
        CREATE FUNCTION stf_projection_immutable() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'STF verified projections are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER stf_findings_no_change BEFORE UPDATE OR DELETE ON stf_findings "
        "FOR EACH ROW EXECUTE FUNCTION stf_projection_immutable()"
    )
    op.execute(
        "CREATE TRIGGER stf_qualifications_no_change BEFORE UPDATE OR DELETE ON stf_qualifications "
        "FOR EACH ROW EXECUTE FUNCTION stf_projection_immutable()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS stf_qualifications_no_change ON stf_qualifications")
    op.execute("DROP TRIGGER IF EXISTS stf_findings_no_change ON stf_findings")
    op.drop_table("stf_qualifications")
    op.drop_index("ix_stf_findings_action_id", table_name="stf_findings")
    op.drop_index("ix_stf_findings_run_id", table_name="stf_findings")
    op.drop_table("stf_findings")
    op.execute("DROP FUNCTION IF EXISTS stf_projection_immutable()")
