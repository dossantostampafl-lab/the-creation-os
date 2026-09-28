"""Plain data returned by the transactional repository. No behavior: the database is the authority."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DispatchReceipt:
    """`authorized` is permission to send, not execution; only a gateway `execution_id` later means executed."""

    status: str  # denied | authorized | dispatched | executed | unknown
    execution_id: str | None = None
    reason_codes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    workflow_id: str
    state: str
    desired_state: str
    created: bool


@dataclass(frozen=True)
class OutboxLease:
    id: str
    destination: str
    payload: dict[str, Any]
    token: str
    attempts: int


@dataclass(frozen=True)
class RunView:
    run_id: str
    mission_id: str
    mission_version: int
    state: str
    desired_state: str
    plan_hash: str
    workflow_id: str

    def as_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "mission_id": self.mission_id, "mission_version": self.mission_version,
                "state": self.state, "desired_state": self.desired_state, "plan_hash": self.plan_hash,
                "workflow_id": self.workflow_id}


@dataclass(frozen=True)
class ApprovalRecord:
    id: str
    creator_id: str
    run_id: str
    action_id: str
    parameters_hash: str
    expires_at: Any
    decision: str
