"""Allow execution_reclaimed in agent_execution_events.event_type.

Revision ID: 0033_ff_reclaimed
Revises: 0032_ff_memory_vector
Create Date: 2026-08-02 00:00:00.000000

Lote P4/P5 (concorrência real de worker) found that a worker killed after
AgentExecutionService.create() succeeds but before acknowledge()/fail()
leaves an orphaned agent_executions row at (dispatch_item_id,
attempt_number) — a real lease-expiry reclaim by another worker then hits
that row and, since inserting a second row for the same key always
violates uq_execution_dispatch_attempt, create() resumes the existing row
instead of inserting a new one. That lote reused the existing
"execution_created" event_type for the resumed row rather than extending
this CHECK constraint without authorization (see ARCHITECTURE.md, Lote:
P4/P5). This migration adds the dedicated "execution_reclaimed" value so
the two cases are distinguishable in agent_execution_events, per the
explicit follow-up decision in Lote: event_type dedicado para reclaim de
lease.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision = "0033_ff_reclaimed"
down_revision = "0032_ff_memory_vector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_execution_event_type", "agent_execution_events", type_="check")
    op.create_check_constraint(
        "ck_execution_event_type",
        "agent_execution_events",
        "event_type IN ('execution_created','execution_reclaimed','execution_accepted','execution_started',"
        "'execution_succeeded','execution_failed','execution_cancelled','execution_timed_out','result_returned')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_execution_event_type", "agent_execution_events", type_="check")
    op.create_check_constraint(
        "ck_execution_event_type",
        "agent_execution_events",
        "event_type IN ('execution_created','execution_accepted','execution_started','execution_succeeded',"
        "'execution_failed','execution_cancelled','execution_timed_out','result_returned')",
    )
