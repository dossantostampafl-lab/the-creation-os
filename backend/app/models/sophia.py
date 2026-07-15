from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import uuid_string


class SophiaUnderstanding(Base):
    __tablename__ = "sophia_understandings"
    __table_args__ = (
        UniqueConstraint("god_interaction_id", name="uq_sophia_understanding_god_interaction"),
        CheckConstraint(
            (
                "understanding_type IN ("
                "'DIRECT_UNDERSTANDING','INFORMATIONAL_UNDERSTANDING',"
                "'POTENTIAL_UNDERSTANDING','UNSUPPORTED_UNDERSTANDING')"
            ),
            name="ck_sophia_understanding_type",
        ),
        CheckConstraint("char_length(source_fingerprint) = 64", name="ck_sophia_source_fingerprint"),
        CheckConstraint("char_length(understanding_fingerprint) = 64", name="ck_sophia_understanding_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    god_interaction_id: Mapped[str] = mapped_column(ForeignKey("god_conversation_interactions.id"), nullable=False)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    understanding_type: Mapped[str] = mapped_column(String(40), nullable=False)
    understanding_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    understanding_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    understood_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
