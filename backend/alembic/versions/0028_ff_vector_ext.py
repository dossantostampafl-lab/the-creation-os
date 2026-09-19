"""pgvector extension

Revision ID: 0028_ff_vector_ext
Revises: 0027_ff_mission_auth
Create Date: 2026-07-19 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision = "0028_ff_vector_ext"
down_revision = "0027_ff_mission_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector;")
