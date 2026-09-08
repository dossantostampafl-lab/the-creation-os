"""Enforce conscious-memory provenance and authority separation.

Revision ID: 0008_memory_provenance
Revises: 0007_projection_checkpoints
"""
from __future__ import annotations

from alembic import op

revision = "0008_memory_provenance"
down_revision = "0007_projection_checkpoints"
branch_labels = None
depends_on = None

_ALLOWED_SOURCE_TYPES = (
    "conversation",
    "message",
    "inception",
    "mission",
    "task",
    "agent_execution",
    "capability_invocation",
)


def upgrade() -> None:
    allowed = ", ".join(f"'{item}'" for item in _ALLOWED_SOURCE_TYPES)
    op.create_check_constraint(
        "ck_conscious_memory_source_type",
        "conscious_memory",
        f"source_type IN ({allowed})",
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_conscious_memory_provenance()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            source_exists boolean := false;
        BEGIN
            IF NEW.metadata_json ?| ARRAY[
                'authorized', 'authorization', 'authority', 'permission', 'permissions',
                'allowed_capabilities', 'denied_capabilities', 'creator_approval'
            ] THEN
                RAISE EXCEPTION 'conscious memory cannot assert authority';
            END IF;

            CASE NEW.source_type
                WHEN 'conversation' THEN
                    SELECT EXISTS(SELECT 1 FROM conversations WHERE id = NEW.source_id) INTO source_exists;
                WHEN 'message' THEN
                    SELECT EXISTS(SELECT 1 FROM messages WHERE id = NEW.source_id) INTO source_exists;
                WHEN 'inception' THEN
                    SELECT EXISTS(SELECT 1 FROM inceptions WHERE id = NEW.source_id) INTO source_exists;
                WHEN 'mission' THEN
                    SELECT EXISTS(SELECT 1 FROM missions WHERE id = NEW.source_id) INTO source_exists;
                WHEN 'task' THEN
                    SELECT EXISTS(SELECT 1 FROM tasks WHERE id = NEW.source_id) INTO source_exists;
                WHEN 'agent_execution' THEN
                    SELECT EXISTS(SELECT 1 FROM agent_executions WHERE id = NEW.source_id) INTO source_exists;
                WHEN 'capability_invocation' THEN
                    SELECT EXISTS(SELECT 1 FROM capability_invocations WHERE id = NEW.source_id) INTO source_exists;
                ELSE
                    source_exists := false;
            END CASE;

            IF NOT source_exists THEN
                RAISE EXCEPTION 'conscious memory provenance source does not exist';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_validate_conscious_memory_provenance
        BEFORE INSERT OR UPDATE OF source_type, source_id, metadata_json
        ON conscious_memory
        FOR EACH ROW
        EXECUTE FUNCTION validate_conscious_memory_provenance();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_validate_conscious_memory_provenance ON conscious_memory")
    op.execute("DROP FUNCTION IF EXISTS validate_conscious_memory_provenance()")
    op.drop_constraint("ck_conscious_memory_source_type", "conscious_memory", type_="check")
