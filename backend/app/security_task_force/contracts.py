from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Environment(StrEnum):
    CYBER_RANGE = "CYBER_RANGE"
    REAL_AUTHORIZED = "REAL_AUTHORIZED"


class RiskClass(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"
    R5 = "R5"


class MissionContract(BaseModel):
    mission_id: str
    creator_id: str
    objective: str
    success_criteria: list[str] = Field(min_length=1)
    authorized_targets: list[str] = Field(min_length=1)
    excluded_targets: list[str] = Field(default_factory=list)
    authorized_environments: list[Environment] = Field(min_length=1)
    allowed_action_classes: list[str] = Field(min_length=1)
    risk_ceiling: RiskClass
    time_window: dict[str, datetime]
    resource_budget: dict[str, Any] = Field(default_factory=dict)
    data_handling_class: str = "internal"
    required_evidence: list[str] = Field(default_factory=list)
    rollback_requirements: list[str] = Field(default_factory=list)
    termination_conditions: list[str] = Field(default_factory=list)
    escalation_policy: dict[str, Any] = Field(default_factory=dict)
    requested_specialties: list[str] = Field(default_factory=list)
    mission_version: int = Field(ge=1)

    @model_validator(mode="after")
    def scope_is_consistent(self) -> "MissionContract":
        if set(self.authorized_targets) & set(self.excluded_targets):
            raise ValueError("authorized and excluded targets must not overlap")
        return self


class ActionRequest(BaseModel):
    action_id: str
    mission_id: str
    mission_version: int = Field(ge=1)
    task_id: str
    actor: str
    target_id: str
    environment: Environment
    capability: str
    action_class: str
    risk_class: RiskClass
    parameters: dict[str, Any] = Field(default_factory=dict)
    rollback_reference: str | None = None
    evidence_expectation: list[str] = Field(default_factory=list)
    idempotency_key: str


class AuthorizationDecision(BaseModel):
    decision_id: str
    action_id: str
    decision: str = Field(pattern=r"^(permit|deny|escalate)$")
    policy_version: str
    capability_grant_reference: str | None = None
    conditions: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    reason_codes: list[str] = Field(default_factory=list)
    creator_approval_reference: str | None = None
