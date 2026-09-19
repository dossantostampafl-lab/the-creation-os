"""Mission Planner and Task Graph foundation."""

import sqlalchemy as sa

from alembic import op

revision = "0011_ff_planner"
down_revision = "0010_ff_tree"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("tasks", "step_id", existing_type=sa.String(36), nullable=True)
    op.alter_column("tasks", "universe_id", existing_type=sa.String(36), nullable=True)
    op.alter_column("tasks", "agent_id", existing_type=sa.String(36), nullable=True)
    for column in (
        sa.Column("parent_task_id", sa.String(36), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("name", sa.String(256), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("required_capability_id", sa.String(36), sa.ForeignKey("capabilities.id"), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("state", sa.String(32), nullable=False, server_default=sa.text("'created'")),
        sa.Column("retry_limit", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("300")),
        sa.Column("estimated_duration", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ):
        op.add_column("tasks", column)
    op.execute("UPDATE tasks SET name='legacy-'||id, description='Legacy task', state='created' WHERE name IS NULL")
    op.alter_column("tasks", "name", nullable=False)
    op.alter_column("tasks", "description", nullable=False)
    op.create_check_constraint(
        "ck_task_state", "tasks", "state IN ('created','planned','waiting','ready','blocked','completed','failed','cancelled')"
    )
    op.create_unique_constraint("uq_task_mission_name", "tasks", ["mission_id", "name"])
    op.create_table(
        "task_dependencies",
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("dependency_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("task_id <> dependency_id", name="ck_task_dependency_not_self"),
    )


def downgrade():
    op.drop_table("task_dependencies")
    op.drop_constraint("uq_task_mission_name", "tasks", type_="unique")
    op.drop_constraint("ck_task_state", "tasks", type_="check")
    for name in (
        "updated_at",
        "estimated_duration",
        "timeout_seconds",
        "retry_count",
        "retry_limit",
        "state",
        "priority",
        "required_capability_id",
        "description",
        "name",
        "parent_task_id",
    ):
        op.drop_column("tasks", name)
    op.alter_column("tasks", "agent_id", existing_type=sa.String(36), nullable=False)
    op.alter_column("tasks", "universe_id", existing_type=sa.String(36), nullable=False)
    op.alter_column("tasks", "step_id", existing_type=sa.String(36), nullable=False)
