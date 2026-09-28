from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import uuid_string


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        UniqueConstraint("creator_id", "fingerprint", name="uq_opportunity_creator_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    creator_id: Mapped[str] = mapped_column(ForeignKey("creator.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(256), nullable=False)
    sector: Mapped[str] = mapped_column(String(128), nullable=False)
    problem_or_gap: Mapped[str] = mapped_column(Text, nullable=False)
    capture_mechanism: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_refs_json: Mapped[list] = mapped_column(JSON, nullable=False, server_default=text("'[]'"))
    first_discovered_by_universe_id: Mapped[str] = mapped_column(ForeignKey("universes.id"), nullable=False, index=True)
    time_window_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'DETECTED'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class OpportunityThesis(Base):
    __tablename__ = "opportunity_theses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), nullable=False, index=True)
    universe_id: Mapped[str] = mapped_column(ForeignKey("universes.id"), nullable=False, index=True)
    proposed_value: Mapped[str] = mapped_column(Text, nullable=False)
    target_payer: Mapped[str] = mapped_column(Text, nullable=False)
    capture_path: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_cost_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    expected_value_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    max_downside_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    falsification_conditions_json: Mapped[list] = mapped_column(JSON, nullable=False, server_default=text("'[]'"))
    evidence_refs_json: Mapped[list] = mapped_column(JSON, nullable=False, server_default=text("'[]'"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'PROPOSED'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class OpportunityLease(Base):
    __tablename__ = "opportunity_leases"
    __table_args__ = (
        Index(
            "uq_opportunity_active_executive_lease",
            "opportunity_id",
            unique=True,
            postgresql_where=text("lease_type = 'EXECUTIVE' AND status = 'ACTIVE'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), nullable=False, index=True)
    thesis_id: Mapped[str] = mapped_column(ForeignKey("opportunity_theses.id"), nullable=False, index=True)
    universe_id: Mapped[str] = mapped_column(ForeignKey("universes.id"), nullable=False, index=True)
    lease_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'ACTIVE'"))
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
