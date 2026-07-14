from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import uuid_string


class MissionConsolidation(Base):
    __tablename__ = "mission_consolidations"
    __table_args__ = (
        UniqueConstraint("mission_id", name="uq_mission_consolidation_mission"),
        CheckConstraint("status IN ('complete')", name="ck_mission_consolidation_status"),
        CheckConstraint("char_length(fingerprint) = 64", name="ck_mission_consolidation_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    inconsistencies_json: Mapped[list] = mapped_column(JSON, nullable=False, server_default=text("'[]'"))
    completeness_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
