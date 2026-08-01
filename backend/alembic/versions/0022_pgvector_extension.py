"""pgvector extension

Revision ID: 0022_pgvector_extension
Revises: 0021_mission_authorization
Create Date: 2026-07-19 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022_pgvector_extension"
down_revision: str | None = "0021_mission_authorization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector;")
