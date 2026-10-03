from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import uuid_string


class KnowledgeProject(Base):
    __tablename__ = "knowledge_projects"
    __table_args__ = (UniqueConstraint("id", "creator_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    creator_id: Mapped[str] = mapped_column(ForeignKey("creator.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))

class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"
    __table_args__ = (UniqueConstraint("id", "creator_id"), ForeignKeyConstraint(["project_id", "creator_id"], ["knowledge_projects.id", "knowledge_projects.creator_id"]))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    creator_id: Mapped[str] = mapped_column(ForeignKey("creator.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_revision_id: Mapped[str] = mapped_column(String(36))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class KnowledgeRevision(Base):
    __tablename__ = "knowledge_revisions"
    __table_args__ = (UniqueConstraint("id", "creator_id"), UniqueConstraint("item_id", "ordinal"), ForeignKeyConstraint(["item_id", "creator_id"], ["knowledge_items.id", "knowledge_items.creator_id"], ondelete="CASCADE"), Index("ix_knowledge_search", "search_vector", postgresql_using="gin"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    creator_id: Mapped[str] = mapped_column(String(36), index=True)
    item_id: Mapped[str] = mapped_column(String(36), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(32))
    epistemic_state: Mapped[str] = mapped_column(String(16))
    lifecycle: Mapped[str] = mapped_column(String(16), default="active")
    source_type: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    search_vector: Mapped[Any] = mapped_column(TSVECTOR, Computed("to_tsvector('portuguese'::regconfig, title || ' ' || content)", persisted=True))

class KnowledgeDependency(Base):
    __tablename__ = "knowledge_dependencies"
    __table_args__ = (ForeignKeyConstraint(["revision_id", "creator_id"], ["knowledge_revisions.id", "knowledge_revisions.creator_id"], ondelete="CASCADE"), ForeignKeyConstraint(["source_revision_id", "creator_id"], ["knowledge_revisions.id", "knowledge_revisions.creator_id"], ondelete="CASCADE"))
    revision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_revision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    creator_id: Mapped[str] = mapped_column(String(36))

class KnowledgeRelation(Base):
    __tablename__ = "knowledge_relations"
    __table_args__ = (ForeignKeyConstraint(["from_id", "creator_id"], ["knowledge_items.id", "knowledge_items.creator_id"], ondelete="CASCADE"), ForeignKeyConstraint(["to_id", "creator_id"], ["knowledge_items.id", "knowledge_items.creator_id"], ondelete="CASCADE"), UniqueConstraint("from_id", "to_id", "kind"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    creator_id: Mapped[str] = mapped_column(String(36))
    from_id: Mapped[str] = mapped_column(String(36))
    to_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(32))

class KnowledgeOutbox(Base):
    __tablename__ = "knowledge_outbox"
    __table_args__ = (UniqueConstraint("creator_id", "request_key"),)
    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    creator_id: Mapped[str] = mapped_column(ForeignKey("creator.id", ondelete="CASCADE"))
    request_key: Mapped[str] = mapped_column(String(200))
    payload_hash: Mapped[str] = mapped_column(String(64))
    item_id: Mapped[str] = mapped_column(ForeignKey("knowledge_items.id", ondelete="CASCADE"))
    revision_id: Mapped[str] = mapped_column(ForeignKey("knowledge_revisions.id", ondelete="CASCADE"))

class KnowledgeReceipt(Base):
    __tablename__ = "knowledge_receipts"
    consumer: Mapped[str] = mapped_column(String(64), primary_key=True)
    sequence: Mapped[int] = mapped_column(ForeignKey("knowledge_outbox.sequence", ondelete="CASCADE"), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

class KnowledgeEpoch(Base):
    __tablename__ = "knowledge_epochs"
    creator_id: Mapped[str] = mapped_column(ForeignKey("creator.id", ondelete="CASCADE"), primary_key=True)
    version: Mapped[int] = mapped_column(BigInteger, default=1)

class ContextTrace(Base):
    __tablename__ = "deus_context_traces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    creator_id: Mapped[str] = mapped_column(ForeignKey("creator.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

class ConversationTurn(Base):
    __tablename__ = "deus_conversation_turns"
    __table_args__ = (UniqueConstraint("conversation_id", "request_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    request_id: Mapped[str] = mapped_column(String(36))
    content_hash: Mapped[str] = mapped_column(String(64))
    owner: Mapped[str] = mapped_column(String(36))
    state: Mapped[str] = mapped_column(String(16), default="pending")
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
