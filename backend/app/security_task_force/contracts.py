from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# An environment is always named, never implied: a Range zone or one approved real environment.
# A grant issued for one identifier is worthless in every other one.
ENVIRONMENT_ID = re.compile(r"^(cyber_range|real):[a-z0-9][a-z0-9._-]{0,63}$")


def is_environment_id(value: str) -> bool:
    return ENVIRONMENT_ID.fullmatch(value) is not None


class RiskClass(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"
    R5 = "R5"

    @property
    def rank(self) -> int:
        return int(self.value[1])


class MissionState(StrEnum):
    DRAFT = "DRAFT"
    COMPILED = "COMPILED"
    AUTHORIZED = "AUTHORIZED"
    RUNNING = "RUNNING"
    AWAITING_CREATOR = "AWAITING_CREATOR"
    VERIFYING = "VERIFYING"
    CANCELLING = "CANCELLING"
    UNKNOWN = "UNKNOWN"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


TERMINAL_STATES = frozenset({MissionState.COMPLETED, MissionState.ABORTED})

_TRANSITIONS: dict[MissionState, frozenset[MissionState]] = {
    MissionState.DRAFT: frozenset({MissionState.COMPILED, MissionState.ABORTED}),
    MissionState.COMPILED: frozenset({MissionState.AUTHORIZED, MissionState.ABORTED}),
    MissionState.AUTHORIZED: frozenset({MissionState.RUNNING, MissionState.ABORTED}),
    MissionState.RUNNING: frozenset({MissionState.AWAITING_CREATOR, MissionState.VERIFYING, MissionState.CANCELLING,
                                     MissionState.UNKNOWN, MissionState.ABORTED}),
    MissionState.AWAITING_CREATOR: frozenset({MissionState.RUNNING, MissionState.CANCELLING, MissionState.ABORTED}),
    MissionState.VERIFYING: frozenset({MissionState.COMPLETED, MissionState.CANCELLING, MissionState.UNKNOWN,
                                       MissionState.ABORTED}),
    # Cancelling ends only after reconciliation; an unknown outcome is resolved or aborted, never completed.
    MissionState.CANCELLING: frozenset({MissionState.UNKNOWN, MissionState.ABORTED}),
    MissionState.UNKNOWN: frozenset({MissionState.CANCELLING, MissionState.ABORTED}),
    MissionState.COMPLETED: frozenset(),
    MissionState.ABORTED: frozenset(),
}


def can_transition(current: MissionState, target: MissionState) -> bool:
    return target in _TRANSITIONS[current]


def _unique(values: list[str]) -> list[str]:
    return sorted({value.strip() for value in values if value.strip()})


class MissionContract(BaseModel):
    mission_id: str = Field(min_length=1)
    creator_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    success_criteria: list[str] = Field(min_length=1)
    authorized_targets: list[str] = Field(min_length=1)
    excluded_targets: list[str] = Field(default_factory=list)
    authorized_environments: list[str] = Field(min_length=1)
    allowed_action_classes: list[str] = Field(min_length=1)
    risk_ceiling: RiskClass
    time_window: dict[str, datetime] = Field(default_factory=dict)
    resource_budget: dict[str, Any] = Field(default_factory=dict)
    data_handling_class: str = "internal"
    required_evidence: list[str] = Field(default_factory=list)
    rollback_requirements: list[str] = Field(default_factory=list)
    termination_conditions: list[str] = Field(default_factory=list)
    escalation_policy: dict[str, Any] = Field(default_factory=dict)
    requested_specialties: list[str] = Field(default_factory=list)
    mission_version: int = Field(default=1, ge=1)

    @field_validator("authorized_targets", "excluded_targets", "allowed_action_classes", mode="after")
    @classmethod
    def _normalize_lists(cls, value: list[str]) -> list[str]:
        return _unique(value)

    @field_validator("authorized_environments", mode="after")
    @classmethod
    def _normalize_environments(cls, value: list[str]) -> list[str]:
        environments = _unique(value)
        invalid = [item for item in environments if not is_environment_id(item)]
        if invalid:
            raise ValueError(f"environment ids must look like cyber_range:<zone> or real:<id>: {invalid}")
        if not environments:
            raise ValueError("at least one authorized environment is required")
        return environments

    @field_validator("time_window", mode="after")
    @classmethod
    def _time_window_is_ordered(cls, value: dict[str, datetime]) -> dict[str, datetime]:
        if value and (set(value) != {"start", "end"} or value["start"] >= value["end"]):
            raise ValueError("time_window needs start before end")
        # The policy engine compares nanoseconds since the epoch, which only reaches the year 2262.
        if value and not all(2000 <= moment.year <= 2200 for moment in value.values()):
            raise ValueError("time_window must fall between the years 2000 and 2200")
        return value

    @model_validator(mode="after")
    def _scope_is_consistent(self) -> "MissionContract":
        if not self.authorized_targets:
            raise ValueError("at least one authorized target is required")
        if set(self.authorized_targets) & set(self.excluded_targets):
            raise ValueError("authorized and excluded targets must not overlap")
        if self.risk_ceiling is RiskClass.R5:
            raise ValueError("R5 is a new mission, never a ceiling")
        return self

    def normalized_payload(self) -> dict[str, Any]:
        """The contract as recursively key-sorted JSON, the form that gets hashed and signed."""
        return json.loads(json.dumps(self.model_dump(mode="json"), sort_keys=True))


class ActionRequest(BaseModel):
    action_id: str = Field(min_length=1)
    mission_id: str = Field(min_length=1)
    mission_version: int = Field(ge=1)
    task_id: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    environment_id: str
    capability: str = Field(min_length=1)
    action_class: str = Field(min_length=1)
    risk_class: RiskClass
    parameters: dict[str, Any] = Field(default_factory=dict)
    rollback_reference: str | None = None
    evidence_expectation: list[str] = Field(default_factory=list)
    idempotency_key: str = Field(min_length=1)

    @field_validator("environment_id")
    @classmethod
    def _environment_is_explicit(cls, value: str) -> str:
        if not is_environment_id(value):
            raise ValueError("environment_id must look like cyber_range:<zone> or real:<id>")
        return value


class AuthorizationDecision(BaseModel):
    decision_id: str
    action_id: str
    decision: str = Field(pattern=r"^(permit|deny|escalate)$")
    policy_version: str
    environment_id: str | None = None
    capability_grant_reference: str | None = None
    conditions: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    reason_codes: list[str] = Field(default_factory=list)
    creator_approval_reference: str | None = None


class CapabilityGrant(BaseModel):
    """Ephemeral authority for one actor, one capability, one target, one environment."""

    model_config = ConfigDict(frozen=True)

    grant_id: str
    mission_id: str
    mission_version: int = Field(ge=1)
    actor: str
    capability: str
    target_id: str
    environment_id: str
    action_class: str
    expires_at: datetime
    max_invocations: int = Field(default=1, ge=1)
    revoked: bool = False

    def matches(self, action: ActionRequest, *, invocations: int = 0, now: datetime | None = None) -> bool:
        moment = now or datetime.now(timezone.utc)
        return (
            not self.revoked
            and self.expires_at > moment
            and invocations < self.max_invocations
            and self.mission_id == action.mission_id
            and self.mission_version == action.mission_version
            and self.actor == action.actor
            and self.capability == action.capability
            and self.target_id == action.target_id
            and self.environment_id == action.environment_id
            and self.action_class == action.action_class
        )
