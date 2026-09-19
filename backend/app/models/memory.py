from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import uuid_string


class CreatorMemory(Base):
    """DEPRECATED (Lote: Convergência de memória de conversa, 2026-08-01):
    GodConversationService no longer reads from this table — see
    app/repositories/god.py's conversation_memory_candidates() and
    ARCHITECTURE.md. The table, model, and app/repositories/memory.py /
    app/services/memory.py / the POST+GET /memory HTTP routes
    (app/api/memory.py) all remain fully functional and are not removed in
    this lote; physical removal is a separate future cleanup lote, only
    after confirming the convergence works in production with no
    regression. Any new memory written here via POST /memory is presently
    NOT visible to GOD — see the pendência in ARCHITECTURE.md.
    """

    __tablename__ = "creator_memories"
    __table_args__ = (
        CheckConstraint(
            "memory_type IN ('EPISODIC','SEMANTIC','OPERATIONAL','CREATOR')",
            name="ck_creator_memory_type",
        ),
        CheckConstraint("importance BETWEEN 1 AND 10", name="ck_creator_memory_importance"),
        CheckConstraint("char_length(memory_fingerprint) = 64", name="ck_creator_memory_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    creator_id: Mapped[str] = mapped_column(ForeignKey("creator.id"), nullable=False)
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    memory_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
