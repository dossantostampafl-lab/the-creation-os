"""Agent Dispatcher Protocol."""

import sqlalchemy as sa

from alembic import op

revision = "0007_agent_dispatcher_protocol"
down_revision = "0006_dispatch_queue"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("worker_uuid", sa.String(36), nullable=False, unique=True),
        sa.Column("worker_name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("credential_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="registered"),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True)),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('registered','available','busy','offline','retired')", name="ck_worker_status"),
    )
    op.create_index("ix_workers_status_heartbeat", "workers", ["status", "last_heartbeat"])
    op.create_table(
        "worker_capabilities",
        sa.Column("worker_id", sa.String(36), sa.ForeignKey("workers.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("capability_id", sa.String(36), sa.ForeignKey("capabilities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade():
    op.drop_table("worker_capabilities")
    op.drop_index("ix_workers_status_heartbeat", table_name="workers")
    op.drop_table("workers")
