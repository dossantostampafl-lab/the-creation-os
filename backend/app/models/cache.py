from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, DateTime, Float, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def uuid_string() -> str:
    return str(uuid.uuid4())


class SemanticCacheEntry(Base):
    __tablename__ = "semantic_cache_entries"
    __table_args__ = (UniqueConstraint("exact_key", name="uq_semantic_cache_exact_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    creator_scope: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    universe_scope: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    intent_class: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sensitivity: Mapped[str] = mapped_column(String(32), nullable=False)
    normalized_query: Mapped[str] = mapped_column(Text, nullable=False)
    exact_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    context_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    knowledge_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    retrieval_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generation_profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    authorization_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_state_class: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'VALIDATED'"))
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("1.0"))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(128)), nullable=False, server_default=text("'{}'"))
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class CacheEvent(Base):
    __tablename__ = "cache_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    cache_entry_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    creator_scope: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    semantic_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
