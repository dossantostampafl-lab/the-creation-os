from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import uuid_string


class AutomationExecution(Base):
    __tablename__ = "automation_executions"
    __table_args__ = (
        UniqueConstraint("creator_id", "connector_id", "idempotency_key", name="uq_automation_execution_idempotency"),
        CheckConstraint(
            "status IN ('SUCCEEDED','FAILED','TIMEOUT','REJECTED')",
            name="ck_automation_execution_status",
        ),
        CheckConstraint("char_length(request_fingerprint) = 64", name="ck_automation_execution_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    creator_id: Mapped[str] = mapped_column(ForeignKey("creator.id"), nullable=False)
    connector_id: Mapped[str] = mapped_column(String(128), nullable=False)
    capability: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result_payload: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
