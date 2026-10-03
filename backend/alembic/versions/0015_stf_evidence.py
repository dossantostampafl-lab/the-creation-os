"""Persist immutable Security Task Force evidence.

Revision ID: 0015_stf_evidence
Revises: 0014_diagnostic_incidents
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0015_stf_evidence"
down_revision = "0014_diagnostic_incidents"
branch_labels = None
depends_on = None

EVIDENCE_KINDS = ("execution", "attack", "defense")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.create_table(
        "stf_evidence",
        sa.Column("evidence_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("execution_id", sa.String(36), nullable=False),
        sa.Column("mission_id", sa.String(128), nullable=False),
        sa.Column("action_id", sa.String(128), nullable=False),
        sa.Column("task_id", sa.String(128), nullable=False),
        sa.Column("environment_id", sa.String(128), nullable=False),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("acquired_at", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["stf_runs.id"]),
        sa.ForeignKeyConstraint(["execution_id"], ["stf_dispatches.execution_id"]),
        sa.PrimaryKeyConstraint("evidence_id"),
        sa.CheckConstraint(_in("kind", EVIDENCE_KINDS), name="ck_stf_evidence_kind"),
    )
    op.create_index("ix_stf_evidence_run_id", "stf_evidence", ["run_id"])
    op.create_index("ix_stf_evidence_execution_id", "stf_evidence", ["execution_id"])
    op.create_index("ix_stf_evidence_action_id", "stf_evidence", ["action_id"])
    op.execute(
        """
        CREATE FUNCTION stf_evidence_immutable() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'stf_evidence rows are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER stf_evidence_no_change BEFORE UPDATE OR DELETE ON stf_evidence "
        "FOR EACH ROW EXECUTE FUNCTION stf_evidence_immutable()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS stf_evidence_no_change ON stf_evidence")
    op.drop_table("stf_evidence")
    op.execute("DROP FUNCTION IF EXISTS stf_evidence_immutable()")
