"""Living Core domain invariants and audit metadata.

Revision ID: 0002_living_core_domain
Revises: 0001_initial
"""
import sqlalchemy as sa

from alembic import op

revision = "0002_living_core_domain"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("actor_id", sa.String(36), nullable=True))
    op.add_column("messages", sa.Column("correlation_id", sa.String(36), nullable=True))
    op.execute("UPDATE messages m SET actor_id = c.creator_id, correlation_id = m.id FROM conversations c WHERE c.id = m.conversation_id")
    op.alter_column("messages", "actor_id", nullable=False)
    op.alter_column("messages", "correlation_id", nullable=False)

    op.add_column("missions", sa.Column("creator_id", sa.String(36), nullable=True))
    op.add_column("missions", sa.Column("authorization_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.execute("UPDATE missions m SET creator_id = c.creator_id FROM inceptions i JOIN conversations c ON c.id = i.conversation_id WHERE i.id = m.inception_id")
    op.alter_column("missions", "creator_id", nullable=False)
    op.create_foreign_key("fk_missions_creator", "missions", "creator", ["creator_id"], ["id"])

    op.add_column("chronicles", sa.Column("actor_role", sa.String(64), nullable=True))
    op.execute("UPDATE chronicles SET actor_role = actor_type")
    op.alter_column("chronicles", "actor_role", nullable=False)

    op.execute("UPDATE conversations SET status = lower(status)")
    op.execute("UPDATE inceptions SET status = lower(status)")
    op.execute("UPDATE missions SET status = lower(status)")


def downgrade() -> None:
    op.drop_column("chronicles", "actor_role")
    op.drop_constraint("fk_missions_creator", "missions", type_="foreignkey")
    op.drop_column("missions", "authorization_json")
    op.drop_column("missions", "creator_id")
    op.drop_column("messages", "correlation_id")
    op.drop_column("messages", "actor_id")
