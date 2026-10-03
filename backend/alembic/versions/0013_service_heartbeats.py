"""Durable, expiring service heartbeat per worker boot."""
import sqlalchemy as sa

from alembic import op

revision = '0013_service_heartbeats'
down_revision = '0012_deus_knowledge'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('service_heartbeats',
        sa.Column('service', sa.String(64), primary_key=True),
        sa.Column('boot_id', sa.String(36), primary_key=True),
        sa.Column('lease_owner', sa.String(36), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=False),
        sa.Column('metrics', sa.JSON(), nullable=False))
    op.create_index('ix_service_heartbeats_valid_until', 'service_heartbeats', ['valid_until'])


def downgrade():
    op.drop_table('service_heartbeats')
