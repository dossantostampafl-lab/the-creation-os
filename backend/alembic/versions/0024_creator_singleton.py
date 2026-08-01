"""Enforce at most one row in creator at the database level.

Revision ID: 0024_creator_singleton
Revises: 0023_universe_agent_seed
Create Date: 2026-07-21 00:00:00.000000

Rule 1 of the constitution ("Somente o Criador possui controle total sobre
GOD") depends on exactly one Creator ever existing. Before this migration,
`creator` only had a UNIQUE constraint on `username` — nothing prevented two
concurrent POST /api/v1/auth/bootstrap requests from both observing "no
Creator exists yet" and both inserting a row, since
AuthService.bootstrap() (backend/app/services/auth.py) did a plain
check-then-insert with no row lock and no database-level guard.

This uses the standard Postgres "singleton table" pattern: a boolean column
that can only ever be `true`, with a UNIQUE constraint on it. A second row
can never satisfy `singleton = true` alongside an existing one, so the
second INSERT fails with a UNIQUE violation regardless of application-level
locking. This mirrors the safety net already used elsewhere in this
codebase (row lock + IntegrityError fallback in DecisionService.decide();
pg_advisory_xact_lock in DomainRepository.add_event() for Chronicles).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024_creator_singleton"
down_revision: str | None = "0023_universe_agent_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "creator",
        sa.Column("singleton", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_check_constraint("ck_creator_singleton_true", "creator", "singleton IS TRUE")
    op.create_unique_constraint("uq_creator_singleton", "creator", ["singleton"])


def downgrade() -> None:
    op.drop_constraint("uq_creator_singleton", "creator", type_="unique")
    op.drop_constraint("ck_creator_singleton_true", "creator", type_="check")
    op.drop_column("creator", "singleton")
