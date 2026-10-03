from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import uuid_string

RUN_STATES = ("QUEUED", "RUNNING", "AWAITING_CREATOR", "VERIFYING", "CANCELLING", "UNKNOWN", "COMPLETED", "ABORTED")
DISPATCH_STATUSES = ("denied", "authorized", "dispatched", "executed", "unknown")
EVIDENCE_KINDS = ("execution", "attack", "defense")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class StfContract(Base):
    """A compiled Mission contract. Immutable: a different contract is a new mission_version."""

    __tablename__ = "stf_contracts"
    __table_args__ = (UniqueConstraint("creator_id", "mission_id", "mission_version", name="uq_stf_contract_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    creator_id: Mapped[str] = mapped_column(ForeignKey("creator.id"), nullable=False, index=True)
    mission_id: Mapped[str] = mapped_column(String(128), nullable=False)
    mission_version: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    compiler_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class StfRun(Base):
    __tablename__ = "stf_runs"
    __table_args__ = (
        UniqueConstraint("creator_id", "mission_id", "request_key", name="uq_stf_run_request"),
        CheckConstraint(_in("state", RUN_STATES), name="ck_stf_run_state"),
        CheckConstraint(_in("desired_state", ("RUN", "CANCEL")), name="ck_stf_run_desired_state"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    creator_id: Mapped[str] = mapped_column(ForeignKey("creator.id"), nullable=False, index=True)
    mission_id: Mapped[str] = mapped_column(String(128), nullable=False)
    mission_version: Mapped[int] = mapped_column(Integer, nullable=False)
    request_key: Mapped[str] = mapped_column(String(256), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_json: Mapped[list] = mapped_column(JSON, nullable=False, server_default=text("'[]'"))
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'QUEUED'"))
    desired_state: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'RUN'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class StfGrant(Base):
    __tablename__ = "stf_grants"
    __table_args__ = (
        CheckConstraint("invocations >= 0 AND invocations <= max_invocations", name="ck_stf_grant_budget"),
    )

    grant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("stf_runs.id"), nullable=False, index=True)
    mission_id: Mapped[str] = mapped_column(String(128), nullable=False)
    mission_version: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    capability: Mapped[str] = mapped_column(String(128), nullable=False)
    target_id: Mapped[str] = mapped_column(String(256), nullable=False)
    environment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action_class: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_invocations: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    invocations: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class StfDispatch(Base):
    __tablename__ = "stf_dispatches"
    __table_args__ = (
        UniqueConstraint("run_id", "action_id", name="uq_stf_dispatch_action"),
        UniqueConstraint("run_id", "idempotency_key", name="uq_stf_dispatch_key"),
        CheckConstraint(_in("status", DISPATCH_STATUSES), name="ck_stf_dispatch_status"),
    )

    execution_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    run_id: Mapped[str] = mapped_column(ForeignKey("stf_runs.id"), nullable=False, index=True)
    action_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    grant_id: Mapped[str] = mapped_column(ForeignKey("stf_grants.grant_id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason_codes: Mapped[list] = mapped_column(JSON, nullable=False, server_default=text("'[]'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class StfEvidence(Base):
    """Immutable, redacted evidence correlated to one persisted dispatch."""

    __tablename__ = "stf_evidence"
    __table_args__ = (
        CheckConstraint(_in("kind", EVIDENCE_KINDS), name="ck_stf_evidence_kind"),
    )

    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("stf_runs.id"), nullable=False, index=True)
    execution_id: Mapped[str] = mapped_column(ForeignKey("stf_dispatches.execution_id"), nullable=False, index=True)
    mission_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    environment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    acquired_at: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class StfApproval(Base):
    __tablename__ = "stf_approvals"
    __table_args__ = (CheckConstraint(_in("decision", ("approve", "deny")), name="ck_stf_approval_decision"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    creator_id: Mapped[str] = mapped_column(ForeignKey("creator.id"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("stf_runs.id"), nullable=False, index=True)
    action_id: Mapped[str] = mapped_column(String(128), nullable=False)
    parameters_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class StfOutbox(Base):
    __tablename__ = "stf_outbox"
    __table_args__ = (CheckConstraint(_in("status", ("pending", "leased", "acked", "dead")), name="ck_stf_outbox_status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    destination: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'pending'"))
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class StfInbox(Base):
    __tablename__ = "stf_inbox"

    consumer: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
