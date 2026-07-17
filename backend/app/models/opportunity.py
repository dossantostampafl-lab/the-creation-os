from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def uuid_string() -> str:
    return str(uuid.uuid4())


class OpportunityObservation(Base):
    __tablename__ = "opportunity_observations"
    __table_args__ = (UniqueConstraint("observation_fingerprint", name="uq_opportunity_observation_fingerprint"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    universe: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    subject: Mapped[str] = mapped_column(String(256), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    normalized_data: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    source_reliability: Mapped[float] = mapped_column(Float, nullable=False)
    correlation_key: Mapped[str] = mapped_column(String(256), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    observation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (UniqueConstraint("correlation_key", "status", name="uq_opportunity_active_correlation_status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    universe: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    impact: Mapped[float] = mapped_column(Float, nullable=False)
    urgency: Mapped[float] = mapped_column(Float, nullable=False)
    risk: Mapped[float] = mapped_column(Float, nullable=False)
    source_reliability: Mapped[float] = mapped_column(Float, nullable=False)
    priority_score: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    risks: Mapped[dict] = mapped_column(JSON, nullable=False)
    scoring: Mapped[dict] = mapped_column(JSON, nullable=False)
    correlation_key: Mapped[str] = mapped_column(String(256), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    inception_id: Mapped[str | None] = mapped_column(ForeignKey("inceptions.id"), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=lambda: datetime.now(timezone.utc))

    observations: Mapped[list["OpportunityObservation"]] = relationship("OpportunityObservation", secondary="opportunity_evidence")


class OpportunityEvidence(Base):
    __tablename__ = "opportunity_evidence"

    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True)
    observation_id: Mapped[str] = mapped_column(ForeignKey("opportunity_observations.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
