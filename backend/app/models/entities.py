from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def uuid_string() -> str:
    return str(uuid.uuid4())


class Creator(Base):
    __tablename__ = "creator"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=lambda: datetime.now(timezone.utc))


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    creator_id: Mapped[str] = mapped_column(ForeignKey("creator.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'ACTIVE'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=lambda: datetime.now(timezone.utc))

    messages: Mapped[list["Message"]] = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    route: Mapped[str] = mapped_column(String(32), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="messages")


class Inception(Base):
    __tablename__ = "inceptions"
    __table_args__ = (UniqueConstraint("conversation_id", "source_message_id", name="uq_inception_source"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    source_message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'PROPOSED'"))
    trinity_assessment_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str] = mapped_column(String(36), nullable=True)
    decision_reason: Mapped[str] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    conversation: Mapped[Conversation] = relationship("Conversation")
    source_message: Mapped[Message] = relationship("Message")
    mission: Mapped["Mission"] = relationship("Mission", back_populates="inception", uselist=False)


class Mission(Base):
    __tablename__ = "missions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    inception_id: Mapped[str] = mapped_column(ForeignKey("inceptions.id"), nullable=False, unique=True)
    creator_id: Mapped[str] = mapped_column(ForeignKey("creator.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'drafted'"))
    authorization_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    inception: Mapped[Inception] = relationship("Inception", back_populates="mission")
    plan: Mapped["MissionPlan"] = relationship("MissionPlan", back_populates="mission", uselist=False)
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="mission", cascade="all, delete-orphan")


class MissionPlan(Base):
    __tablename__ = "mission_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False, unique=True)
    strategy: Mapped[str] = mapped_column(Text, nullable=False)
    completion_criteria_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    mission: Mapped[Mission] = relationship("Mission", back_populates="plan")
    steps: Mapped[list["MissionStep"]] = relationship("MissionStep", back_populates="plan", cascade="all, delete-orphan")


class MissionStep(Base):
    __tablename__ = "mission_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    plan_id: Mapped[str] = mapped_column(ForeignKey("mission_plans.id"), nullable=False)
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    universe: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    depends_on_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'[]'"))
    completion_criteria_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'PENDING'"))

    plan: Mapped[MissionPlan] = relationship("MissionPlan", back_populates="steps")
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="step", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False)
    step_id: Mapped[str] = mapped_column(ForeignKey("mission_steps.id"), nullable=False)
    universe_id: Mapped[str] = mapped_column(ForeignKey("universes.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'PENDING'"))
    input_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    output_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    error_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    mission: Mapped[Mission] = relationship("Mission", back_populates="tasks")
    step: Mapped[MissionStep] = relationship("MissionStep", back_populates="tasks")
    universe: Mapped["Universe"] = relationship("Universe")
    agent: Mapped["Agent"] = relationship("Agent")


class Universe(Base):
    __tablename__ = "universes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    agents: Mapped[list["Agent"]] = relationship("Agent", back_populates="universe")


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    universe_id: Mapped[str] = mapped_column(ForeignKey("universes.id"), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    capabilities_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    universe: Mapped[Universe] = relationship("Universe", back_populates="agents")


class ConversationMemory(Base):
    __tablename__ = "conversation_memory"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=lambda: datetime.now(timezone.utc))


class MissionMemory(Base):
    __tablename__ = "mission_memory"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=lambda: datetime.now(timezone.utc))


class UniverseMemory(Base):
    __tablename__ = "universe_memory"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    universe_id: Mapped[str] = mapped_column(ForeignKey("universes.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=lambda: datetime.now(timezone.utc))


class ConsciousMemory(Base):
    __tablename__ = "conscious_memory"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class Chronicle(Base):
    __tablename__ = "chronicles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    event_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=uuid_string)
    position: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    causation_id: Mapped[str] = mapped_column(String(36), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(36), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class PulseMetric(Base):
    __tablename__ = "pulse_metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_value_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
