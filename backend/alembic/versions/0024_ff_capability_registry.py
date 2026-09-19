"""Capability registry persistence."""

import sqlalchemy as sa

from alembic import op

revision = "0024_ff_capability_registry"
down_revision = "0023_ff_automation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "registered_capabilities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("capability_id", sa.String(128), nullable=False, unique=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("connector_id", sa.String(128), nullable=False),
        sa.Column("connector_capability", sa.String(128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("mandatory", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("permissions_json", sa.JSON(), nullable=False),
        sa.Column("dependencies_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("capability_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("char_length(capability_fingerprint) = 64", name="ck_registered_capability_fingerprint"),
    )
    op.create_index("ix_registered_capabilities_connector", "registered_capabilities", ["connector_id", "connector_capability"])
    op.create_index("ix_registered_capabilities_enabled", "registered_capabilities", ["enabled", "mandatory"])


def downgrade():
    op.drop_index("ix_registered_capabilities_enabled", table_name="registered_capabilities")
    op.drop_index("ix_registered_capabilities_connector", table_name="registered_capabilities")
    op.drop_table("registered_capabilities")
