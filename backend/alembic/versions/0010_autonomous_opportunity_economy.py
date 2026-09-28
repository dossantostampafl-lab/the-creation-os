"""Add autonomous opportunities, leases, economic ledger, and dual mission origin.

Revision ID: 0010_autonomous_opportunity_economy
Revises: 0009_semantic_cache
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0010_autonomous_opportunity_economy"
down_revision = "0009_semantic_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("creator_id", sa.String(length=36), nullable=False),
        sa.Column("fingerprint", sa.String(length=256), nullable=False),
        sa.Column("sector", sa.String(length=128), nullable=False),
        sa.Column("problem_or_gap", sa.Text(), nullable=False),
        sa.Column("capture_mechanism", sa.Text(), nullable=False),
        sa.Column("evidence_refs_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("first_discovered_by_universe_id", sa.String(length=36), nullable=False),
        sa.Column("time_window_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'DETECTED'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["creator_id"], ["creator.id"]),
        sa.ForeignKeyConstraint(["first_discovered_by_universe_id"], ["universes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("creator_id", "fingerprint", name="uq_opportunity_creator_fingerprint"),
    )
    op.create_index("ix_opportunities_creator_id", "opportunities", ["creator_id"])
    op.create_index(
        "ix_opportunities_first_discovered_by_universe_id",
        "opportunities",
        ["first_discovered_by_universe_id"],
    )

    op.alter_column("missions", "inception_id", existing_type=sa.String(length=36), nullable=True)
    op.add_column("missions", sa.Column("opportunity_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_missions_opportunity",
        "missions",
        "opportunities",
        ["opportunity_id"],
        ["id"],
    )
    op.create_index("ix_missions_opportunity_id", "missions", ["opportunity_id"])
    op.create_check_constraint(
        "ck_mission_exactly_one_origin",
        "missions",
        "(inception_id IS NOT NULL AND opportunity_id IS NULL) OR "
        "(inception_id IS NULL AND opportunity_id IS NOT NULL)",
    )

    op.create_table(
        "opportunity_theses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("opportunity_id", sa.String(length=36), nullable=False),
        sa.Column("universe_id", sa.String(length=36), nullable=False),
        sa.Column("proposed_value", sa.Text(), nullable=False),
        sa.Column("target_payer", sa.Text(), nullable=False),
        sa.Column("capture_path", sa.Text(), nullable=False),
        sa.Column("estimated_cost_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("expected_value_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("max_downside_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("falsification_conditions_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("evidence_refs_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'PROPOSED'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.ForeignKeyConstraint(["universe_id"], ["universes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_opportunity_theses_opportunity_id", "opportunity_theses", ["opportunity_id"])
    op.create_index("ix_opportunity_theses_universe_id", "opportunity_theses", ["universe_id"])

    op.create_table(
        "opportunity_leases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("opportunity_id", sa.String(length=36), nullable=False),
        sa.Column("thesis_id", sa.String(length=36), nullable=False),
        sa.Column("universe_id", sa.String(length=36), nullable=False),
        sa.Column("lease_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.ForeignKeyConstraint(["thesis_id"], ["opportunity_theses.id"]),
        sa.ForeignKeyConstraint(["universe_id"], ["universes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_opportunity_leases_opportunity_id", "opportunity_leases", ["opportunity_id"])
    op.create_index("ix_opportunity_leases_thesis_id", "opportunity_leases", ["thesis_id"])
    op.create_index("ix_opportunity_leases_universe_id", "opportunity_leases", ["universe_id"])
    op.create_index(
        "uq_opportunity_active_executive_lease",
        "opportunity_leases",
        ["opportunity_id"],
        unique=True,
        postgresql_where=sa.text("lease_type = 'EXECUTIVE' AND status = 'ACTIVE'"),
    )

    op.create_table(
        "economic_ledger_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("creator_id", sa.String(length=36), nullable=False),
        sa.Column("universe_id", sa.String(length=36), nullable=False),
        sa.Column("mission_id", sa.String(length=36), nullable=False),
        sa.Column("opportunity_id", sa.String(length=36), nullable=True),
        sa.Column("entry_type", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("external_reference", sa.String(length=256), nullable=True),
        sa.Column("metadata_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["creator_id"], ["creator.id"]),
        sa.ForeignKeyConstraint(["universe_id"], ["universes.id"]),
        sa.ForeignKeyConstraint(["mission_id"], ["missions.id"]),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_economic_ledger_entries_creator_id", "economic_ledger_entries", ["creator_id"])
    op.create_index("ix_economic_ledger_entries_universe_id", "economic_ledger_entries", ["universe_id"])
    op.create_index("ix_economic_ledger_entries_mission_id", "economic_ledger_entries", ["mission_id"])
    op.create_index("ix_economic_ledger_entries_opportunity_id", "economic_ledger_entries", ["opportunity_id"])


def downgrade() -> None:
    op.drop_table("economic_ledger_entries")
    op.drop_table("opportunity_leases")
    op.drop_table("opportunity_theses")

    op.drop_constraint("ck_mission_exactly_one_origin", "missions", type_="check")
    op.drop_index("ix_missions_opportunity_id", table_name="missions")
    op.drop_constraint("fk_missions_opportunity", "missions", type_="foreignkey")
    op.drop_column("missions", "opportunity_id")
    op.alter_column("missions", "inception_id", existing_type=sa.String(length=36), nullable=False)

    op.drop_table("opportunities")
