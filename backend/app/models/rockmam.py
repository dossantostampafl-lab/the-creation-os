from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import uuid_string


class RockmamPossibilityAssessment(Base):
    __tablename__ = "rockmam_possibility_assessments"
    __table_args__ = (
        UniqueConstraint("sophia_understanding_id", name="uq_rockmam_assessment_sophia_understanding"),
        CheckConstraint(
            "assessment_result IN ('VIABLE','NOT_VIABLE','REQUIRES_CREATOR')",
            name="ck_rockmam_assessment_result",
        ),
        CheckConstraint("char_length(source_fingerprint) = 64", name="ck_rockmam_source_fingerprint"),
        CheckConstraint("char_length(assessment_fingerprint) = 64", name="ck_rockmam_assessment_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    sophia_understanding_id: Mapped[str] = mapped_column(ForeignKey("sophia_understandings.id"), nullable=False)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    assessment_result: Mapped[str] = mapped_column(String(32), nullable=False)
    assessment_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    assessment_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
