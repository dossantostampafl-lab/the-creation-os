from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import uuid_string


class MissionManifestation(Base):
    __tablename__ = "mission_manifestations"
    __table_args__ = (
        UniqueConstraint("mission_id", name="uq_mission_manifestation_mission"),
        UniqueConstraint("decision_id", name="uq_mission_manifestation_decision"),
        CheckConstraint(
            "manifestation_state IN ('PENDING','MANIFESTED','FAILED')",
            name="ck_mission_manifestation_state",
        ),
        CheckConstraint("char_length(manifestation_fingerprint) = 64", name="ck_mission_manifestation_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False)
    decision_id: Mapped[str] = mapped_column(ForeignKey("mission_decisions.id"), nullable=False)
    manifestation_state: Mapped[str] = mapped_column(String(32), nullable=False)
    manifestation_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    manifestation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    audit_metadata: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    manifested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, server_default=text("now()"))
