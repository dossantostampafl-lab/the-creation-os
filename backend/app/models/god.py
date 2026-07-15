from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import uuid_string


class GodConversationInteraction(Base):
    __tablename__ = "god_conversation_interactions"
    __table_args__ = (
        UniqueConstraint("conversation_id", "idempotency_key", name="uq_god_interaction_conversation_idempotency"),
        CheckConstraint(
            "interaction_type IN ('DIRECT_RESPONSE','INFORMATIONAL','POTENTIAL','UNSUPPORTED')",
            name="ck_god_interaction_type",
        ),
        CheckConstraint("char_length(fingerprint) = 64", name="ck_god_interaction_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    creator_message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), nullable=False)
    god_message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    interaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    response_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    potential_detected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
