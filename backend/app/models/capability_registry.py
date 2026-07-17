from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import uuid_string


class RegisteredCapability(Base):
    __tablename__ = "registered_capabilities"
    __table_args__ = (
        CheckConstraint("char_length(capability_fingerprint) = 64", name="ck_registered_capability_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    capability_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    connector_id: Mapped[str] = mapped_column(String(128), nullable=False)
    connector_capability: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    permissions_json: Mapped[list] = mapped_column(JSON, nullable=False)
    dependencies_json: Mapped[list] = mapped_column(JSON, nullable=False, server_default=text("'[]'"))
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    capability_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )
