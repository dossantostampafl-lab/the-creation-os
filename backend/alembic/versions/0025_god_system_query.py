"""Allow SYSTEM_QUERY in god_conversation_interactions.interaction_type.

Revision ID: 0025_god_system_query
Revises: 0024_creator_singleton
Create Date: 2026-08-01 00:00:00.000000

LOTE SYSTEM_QUERY adds a 5th GodInteractionType (app/core/god.py) alongside
the 4 that 0013_god_conversation's ck_god_interaction_type already allowed.
The application-level enum was updated, but this database-level CHECK
constraint hardcodes the same 4 values independently — without this
migration, any real SYSTEM_QUERY interaction fails at commit time with
asyncpg.exceptions.CheckViolationError, caught by GodConversationService as
an IntegrityError and misreported as "could not be persisted atomically".
0013 is already applied to the persistent database (alembic_version =
0024_creator_singleton at the time this was written), so it is corrected
here with a new migration rather than edited in place.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0025_god_system_query"
down_revision: str | None = "0024_creator_singleton"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_god_interaction_type", "god_conversation_interactions", type_="check")
    op.create_check_constraint(
        "ck_god_interaction_type",
        "god_conversation_interactions",
        "interaction_type IN ('DIRECT_RESPONSE','INFORMATIONAL','POTENTIAL','SYSTEM_QUERY','UNSUPPORTED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_god_interaction_type", "god_conversation_interactions", type_="check")
    op.create_check_constraint(
        "ck_god_interaction_type",
        "god_conversation_interactions",
        "interaction_type IN ('DIRECT_RESPONSE','INFORMATIONAL','POTENTIAL','UNSUPPORTED')",
    )
