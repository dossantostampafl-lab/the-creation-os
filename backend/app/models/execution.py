from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import uuid_string


class AgentExecution(Base):
    """Compatibility model for both kernel attempts and durable worker dispatch executions."""

    __tablename__ = "agent_executions"
    __table_args__ = (UniqueConstraint("dispatch_item_id", "attempt_number", name="uq_execution_dispatch_attempt"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)

    # Canonical kernel attempt fields.
    attempt: Mapped[int] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'RUNNING'"))
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    output_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    error_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Durable dispatch/worker execution fields.
    dispatch_item_id: Mapped[str] = mapped_column(ForeignKey("dispatch_items.id"), nullable=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=True)
    worker_id: Mapped[str] = mapped_column(ForeignKey("workers.id"), nullable=True)
    capability_id: Mapped[str] = mapped_column(ForeignKey("capabilities.id"), nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=True)
    handler_name: Mapped[str] = mapped_column(String(128), nullable=True)
    handler_version: Mapped[str] = mapped_column(String(32), nullable=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'pending'"))
    input_payload: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    output_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_warnings: Mapped[list | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    max_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, server_default=text("now()"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=lambda: datetime.now(timezone.utc)
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))


class AgentExecutionEvent(Base):
    __tablename__ = "agent_execution_events"
    __table_args__ = (UniqueConstraint("execution_id", "sequence", name="uq_execution_event_sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    execution_id: Mapped[str] = mapped_column(ForeignKey("agent_executions.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CapabilityInvocation(Base):
    __tablename__ = "capability_invocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    agent_execution_id: Mapped[str | None] = mapped_column(ForeignKey("agent_executions.id"), nullable=True, index=True)
    capability: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_effect: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    idempotency_class: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    authorization_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    request_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    error_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
