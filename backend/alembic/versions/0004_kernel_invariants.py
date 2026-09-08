"""Creation Kernel schema invariants.

Revision ID: 0004_kernel_invariants
Revises: 0003_stabilization
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_kernel_invariants"
down_revision = "0003_stabilization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("conversations", "status", server_default=sa.text("'active'"))
    op.alter_column("inceptions", "status", server_default=sa.text("'proposed'"))
    op.alter_column("missions", "status", server_default=sa.text("'drafted'"))

    op.create_unique_constraint("uq_mission_steps_plan_key", "mission_steps", ["plan_id", "step_key"])
    op.create_unique_constraint("uq_mission_steps_plan_position", "mission_steps", ["plan_id", "position"])

    op.create_unique_constraint(
        "uq_conversation_memory_scope_key",
        "conversation_memory",
        ["conversation_id", "key"],
    )
    op.create_unique_constraint(
        "uq_mission_memory_scope_key",
        "mission_memory",
        ["mission_id", "key"],
    )
    op.create_unique_constraint(
        "uq_universe_memory_scope_key",
        "universe_memory",
        ["universe_id", "key"],
    )

    op.create_check_constraint(
        "ck_task_status",
        "tasks",
        "status IN ('PENDING','READY','RUNNING','SUCCEEDED','FAILED','BLOCKED','CANCELLED')",
    )
    op.create_check_constraint("ck_task_attempt_count_nonnegative", "tasks", "attempt_count >= 0")
    op.create_check_constraint("ck_task_max_attempts_positive", "tasks", "max_attempts > 0")


def downgrade() -> None:
    op.drop_constraint("ck_task_max_attempts_positive", "tasks", type_="check")
    op.drop_constraint("ck_task_attempt_count_nonnegative", "tasks", type_="check")
    op.drop_constraint("ck_task_status", "tasks", type_="check")

    op.drop_constraint("uq_universe_memory_scope_key", "universe_memory", type_="unique")
    op.drop_constraint("uq_mission_memory_scope_key", "mission_memory", type_="unique")
    op.drop_constraint("uq_conversation_memory_scope_key", "conversation_memory", type_="unique")
    op.drop_constraint("uq_mission_steps_plan_position", "mission_steps", type_="unique")
    op.drop_constraint("uq_mission_steps_plan_key", "mission_steps", type_="unique")

    op.alter_column("missions", "status", server_default=sa.text("'PLANNED'"))
    op.alter_column("inceptions", "status", server_default=sa.text("'PROPOSED'"))
    op.alter_column("conversations", "status", server_default=sa.text("'ACTIVE'"))
