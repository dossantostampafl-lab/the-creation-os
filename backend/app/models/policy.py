from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import uuid_string


class MissionDecisionReasoning(Base):
    __tablename__ = "mission_decision_reasoning"
    __table_args__ = (
        UniqueConstraint("decision_id", name="uq_mission_decision_reasoning_decision"),
        CheckConstraint("char_length(fingerprint) = 64", name="ck_mission_decision_reasoning_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    decision_id: Mapped[str] = mapped_column(ForeignKey("mission_decisions.id"), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluation_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    rules_applied: Mapped[list] = mapped_column(JSON, nullable=False)
    consistency_summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    completeness_summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    explanation_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
