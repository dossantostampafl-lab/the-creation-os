"""Tree Core Agent Registry and Capability Engine foundation.

Revision ID: 0004_tree_core_foundation
Revises: 0003_stabilization
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_tree_core_foundation"
down_revision = "0003_stabilization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("agents", "code", existing_type=sa.String(64), nullable=True)
    op.alter_column("agents", "universe_id", existing_type=sa.String(36), nullable=True)
    op.add_column("agents", sa.Column("description", sa.Text(), nullable=False, server_default=sa.text("''")))
    op.add_column("agents", sa.Column("universe", sa.String(64), nullable=True))
    op.execute(
        "UPDATE agents SET universe = COALESCE((SELECT code FROM universes WHERE universes.id = agents.universe_id), 'legacy')"
    )
    op.alter_column("agents", "universe", nullable=False)
    op.add_column("agents", sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("agents", sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'offline'")))
    op.add_column("agents", sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")))
    op.add_column("agents", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agents", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.add_column("agents", sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.create_check_constraint("ck_agent_status", "agents", "status IN ('idle','busy','offline','disabled')")

    op.create_table(
        "capabilities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    op.create_index("uq_capabilities_name_normalized", "capabilities", [sa.text("lower(name)")], unique=True)
    op.create_table(
        "agent_capabilities",
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("capability_id", sa.String(36), sa.ForeignKey("capabilities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_agent_capabilities_capability_id", "agent_capabilities", ["capability_id"])
    op.create_index("ix_agents_eligibility", "agents", ["enabled", "status", "heartbeat_at", "priority"])


def downgrade() -> None:
    op.drop_index("ix_agents_eligibility", table_name="agents")
    op.drop_index("ix_agent_capabilities_capability_id", table_name="agent_capabilities")
    op.drop_table("agent_capabilities")
    op.execute("DROP INDEX IF EXISTS uq_capabilities_name_normalized")
    op.drop_table("capabilities")
    op.drop_constraint("ck_agent_status", "agents", type_="check")
    for column in ("enabled", "updated_at", "heartbeat_at", "version", "status", "priority", "universe", "description"):
        op.drop_column("agents", column)
    op.alter_column("agents", "universe_id", existing_type=sa.String(36), nullable=False)
    op.alter_column("agents", "code", existing_type=sa.String(64), nullable=False)
