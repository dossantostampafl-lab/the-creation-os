from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import uuid_string


class MissionDecision(Base):
    __tablename__ = "mission_decisions"
    __table_args__ = (
        UniqueConstraint("mission_id", name="uq_mission_decision_mission"),
        CheckConstraint(
            "decision IN ('APPROVED','REJECTED','REQUIRES_REVIEW')",
            name="ck_mission_decision_state",
        ),
        CheckConstraint(
            "consolidation_fingerprint IS NULL OR char_length(consolidation_fingerprint) = 64",
            name="ck_mission_decision_fingerprint",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False)
    consolidation_id: Mapped[str | None] = mapped_column(ForeignKey("mission_consolidations.id"), nullable=True)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    justification_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    consolidation_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
