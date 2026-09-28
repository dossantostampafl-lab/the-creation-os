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
