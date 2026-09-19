"""Add context-aware semantic response cache storage.

Revision ID: 0009_semantic_cache
Revises: 0008_memory_provenance
"""
from __future__ import annotations

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_semantic_cache"
down_revision = "0008_memory_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "semantic_cache_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("creator_scope", sa.String(length=64), nullable=False),
        sa.Column("universe_scope", sa.String(length=64), nullable=True),
        sa.Column("intent_class", sa.String(length=64), nullable=False),
        sa.Column("sensitivity", sa.String(length=32), nullable=False),
        sa.Column("normalized_query", sa.Text(), nullable=False),
        sa.Column("exact_key", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding_version", sa.String(length=64), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("context_hash", sa.String(length=64), nullable=False),
        sa.Column("context_version", sa.String(length=128), nullable=True),
        sa.Column("knowledge_version", sa.String(length=128), nullable=True),
        sa.Column("retrieval_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("generation_profile_hash", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("authorization_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("tool_state_class", sa.String(length=64), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column("validation_status", sa.String(length=32), server_default=sa.text("'VALIDATED'"), nullable=False),
        sa.Column("confidence", sa.Float(), server_default=sa.text("1.0"), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String(length=128)), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("hit_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_hit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exact_key", name="uq_semantic_cache_exact_key"),
    )
    op.create_index("ix_semantic_cache_entries_creator_scope", "semantic_cache_entries", ["creator_scope"])
    op.create_index("ix_semantic_cache_entries_universe_scope", "semantic_cache_entries", ["universe_scope"])
    op.create_index("ix_semantic_cache_entries_intent_class", "semantic_cache_entries", ["intent_class"])
    op.create_index("ix_semantic_cache_entries_exact_key", "semantic_cache_entries", ["exact_key"])
    op.create_index("ix_semantic_cache_entries_context_hash", "semantic_cache_entries", ["context_hash"])
    op.create_index("ix_semantic_cache_entries_expires_at", "semantic_cache_entries", ["expires_at"])
    op.create_index("ix_semantic_cache_entries_tags", "semantic_cache_entries", ["tags"], postgresql_using="gin")
    op.execute(
        "CREATE INDEX ix_semantic_cache_embedding_1536_hnsw "
        "ON semantic_cache_entries USING hnsw ((embedding::vector(1536)) vector_cosine_ops) "
        "WHERE embedding_dimensions = 1536"
    )

    op.create_table(
        "cache_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("cache_entry_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("creator_scope", sa.String(length=64), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("semantic_score", sa.Float(), nullable=True),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column("metadata_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cache_events_cache_entry_id", "cache_events", ["cache_entry_id"])
    op.create_index("ix_cache_events_event_type", "cache_events", ["event_type"])
    op.create_index("ix_cache_events_creator_scope", "cache_events", ["creator_scope"])


def downgrade() -> None:
    op.drop_index("ix_cache_events_creator_scope", table_name="cache_events")
    op.drop_index("ix_cache_events_event_type", table_name="cache_events")
    op.drop_index("ix_cache_events_cache_entry_id", table_name="cache_events")
    op.drop_table("cache_events")

    op.execute("DROP INDEX IF EXISTS ix_semantic_cache_embedding_1536_hnsw")
    op.drop_index("ix_semantic_cache_entries_tags", table_name="semantic_cache_entries")
    op.drop_index("ix_semantic_cache_entries_expires_at", table_name="semantic_cache_entries")
    op.drop_index("ix_semantic_cache_entries_context_hash", table_name="semantic_cache_entries")
    op.drop_index("ix_semantic_cache_entries_exact_key", table_name="semantic_cache_entries")
    op.drop_index("ix_semantic_cache_entries_intent_class", table_name="semantic_cache_entries")
    op.drop_index("ix_semantic_cache_entries_universe_scope", table_name="semantic_cache_entries")
    op.drop_index("ix_semantic_cache_entries_creator_scope", table_name="semantic_cache_entries")
    op.drop_table("semantic_cache_entries")
    # Keep the vector extension because other application features may depend on it.
