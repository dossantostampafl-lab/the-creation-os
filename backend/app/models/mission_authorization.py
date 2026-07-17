from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def uuid_string() -> str:
    return str(uuid.uuid4())


class MissionAuthorization(Base):
    __tablename__ = "mission_authorizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[str] = mapped_column(String(256), nullable=False)
    creator_id: Mapped[str] = mapped_column(ForeignKey("creator.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    allowed_capabilities_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, server_default=text("'[]'"))
    allowed_resources_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, server_default=text("'[]'"))
    restrictions_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=lambda: datetime.now(timezone.utc))
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    denial_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
