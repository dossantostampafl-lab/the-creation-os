"""Add transactional Security Task Force runtime: contracts, runs, grants, dispatches, outbox, inbox.

Additive only: no existing table is touched.

Revision ID: 0011_stf_runtime
Revises: 0010_opportunity_economy
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011_stf_runtime"
down_revision = "0010_opportunity_economy"
branch_labels = None
depends_on = None

RUN_STATES = ("QUEUED", "RUNNING", "AWAITING_CREATOR", "VERIFYING", "CANCELLING", "UNKNOWN", "COMPLETED", "ABORTED")
DISPATCH_STATUSES = ("denied", "authorized", "dispatched", "executed", "unknown")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _now() -> sa.TextClause:
    return sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "stf_contracts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("creator_id", sa.String(36), nullable=False),
        sa.Column("mission_id", sa.String(128), nullable=False),
        sa.Column("mission_version", sa.Integer(), nullable=False),
        sa.Column("contract_hash", sa.String(64), nullable=False),
        sa.Column("contract_json", sa.JSON(), nullable=False),
        sa.Column("policy_version", sa.String(32), nullable=False),
        sa.Column("compiler_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.ForeignKeyConstraint(["creator_id"], ["creator.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("creator_id", "mission_id", "mission_version", name="uq_stf_contract_version"),
    )
    op.create_index("ix_stf_contracts_creator_id", "stf_contracts", ["creator_id"])
    # A compiled contract is evidence of what was authorized. It is never edited or removed.
    op.execute(
        """
        CREATE FUNCTION stf_contracts_immutable() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'stf_contracts rows are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER stf_contracts_no_change BEFORE UPDATE OR DELETE ON stf_contracts "
        "FOR EACH ROW EXECUTE FUNCTION stf_contracts_immutable()"
    )

    op.create_table(
        "stf_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("creator_id", sa.String(36), nullable=False),
        sa.Column("mission_id", sa.String(128), nullable=False),
        sa.Column("mission_version", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(256), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("plan_hash", sa.String(64), nullable=False),
        sa.Column("plan_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("workflow_id", sa.String(128), nullable=False),
        sa.Column("state", sa.String(32), server_default=sa.text("'QUEUED'"), nullable=False),
        sa.Column("desired_state", sa.String(16), server_default=sa.text("'RUN'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.ForeignKeyConstraint(["creator_id"], ["creator.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("creator_id", "mission_id", "request_key", name="uq_stf_run_request"),
        sa.CheckConstraint(_in("state", RUN_STATES), name="ck_stf_run_state"),
        sa.CheckConstraint(_in("desired_state", ("RUN", "CANCEL")), name="ck_stf_run_desired_state"),
    )
    op.create_index("ix_stf_runs_creator_id", "stf_runs", ["creator_id"])

    op.create_table(
        "stf_grants",
        sa.Column("grant_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("mission_id", sa.String(128), nullable=False),
        sa.Column("mission_version", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("capability", sa.String(128), nullable=False),
        sa.Column("target_id", sa.String(256), nullable=False),
        sa.Column("environment_id", sa.String(128), nullable=False),
        sa.Column("action_class", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_invocations", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("invocations", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("revoked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["stf_runs.id"]),
        sa.PrimaryKeyConstraint("grant_id"),
        sa.CheckConstraint("invocations >= 0 AND invocations <= max_invocations", name="ck_stf_grant_budget"),
    )
    op.create_index("ix_stf_grants_run_id", "stf_grants", ["run_id"])

    op.create_table(
        "stf_dispatches",
        sa.Column("execution_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("action_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("grant_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("evidence_id", sa.String(64), nullable=True),
        sa.Column("reason_codes", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["stf_runs.id"]),
        sa.ForeignKeyConstraint(["grant_id"], ["stf_grants.grant_id"]),
        sa.PrimaryKeyConstraint("execution_id"),
        sa.UniqueConstraint("run_id", "action_id", name="uq_stf_dispatch_action"),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_stf_dispatch_key"),
        sa.CheckConstraint(_in("status", DISPATCH_STATUSES), name="ck_stf_dispatch_status"),
    )
    op.create_index("ix_stf_dispatches_run_id", "stf_dispatches", ["run_id"])
    op.create_index("ix_stf_dispatches_grant_id", "stf_dispatches", ["grant_id"])

    op.create_table(
        "stf_approvals",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("creator_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("action_id", sa.String(128), nullable=False),
        sa.Column("parameters_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.ForeignKeyConstraint(["creator_id"], ["creator.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["stf_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(_in("decision", ("approve", "deny")), name="ck_stf_approval_decision"),
    )
    op.create_index("ix_stf_approvals_creator_id", "stf_approvals", ["creator_id"])
    op.create_index("ix_stf_approvals_run_id", "stf_approvals", ["run_id"])

    op.create_table(
        "stf_outbox",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("destination", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(8), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("lease_token", sa.String(36), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(_in("status", ("pending", "leased", "acked", "dead")), name="ck_stf_outbox_status"),
    )
    op.create_index("ix_stf_outbox_destination", "stf_outbox", ["destination"])

    op.create_table(
        "stf_inbox",
        sa.Column("consumer", sa.String(64), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.PrimaryKeyConstraint("consumer", "event_id"),
    )


def downgrade() -> None:
    op.drop_table("stf_inbox")
    op.drop_table("stf_outbox")
    op.drop_table("stf_approvals")
    op.drop_table("stf_dispatches")
    op.drop_table("stf_grants")
    op.drop_table("stf_runs")
    op.execute("DROP TRIGGER IF EXISTS stf_contracts_no_change ON stf_contracts")
    op.drop_table("stf_contracts")
    op.execute("DROP FUNCTION IF EXISTS stf_contracts_immutable()")
