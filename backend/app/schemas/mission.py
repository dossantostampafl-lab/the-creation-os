from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.core.mission_dag import validate_mission_steps


class MissionCreateRequest(BaseModel):
    inception_id: str = Field(..., min_length=36, max_length=36)
    title: str = Field(..., min_length=3, max_length=256)
    objective: str = Field(..., min_length=1, max_length=8000)


class MissionStepRequest(BaseModel):
    step_key: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    title: str = Field(..., min_length=1, max_length=256)
    description: str = Field(..., min_length=1, max_length=8000)
    universe: str = Field(..., min_length=1, max_length=64)
    position: int = Field(..., ge=1)
    depends_on: list[str] = Field(default_factory=list)
    completion_criteria: dict[str, Any] = Field(default_factory=dict)


class MissionPlanRequest(BaseModel):
    strategy: str = Field(..., min_length=1, max_length=12000)
    steps: list[MissionStepRequest] = Field(..., min_length=1)
    completion_criteria: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_dag(self) -> "MissionPlanRequest":
        validate_mission_steps(self.steps)
        return self


class MissionAuthorizationRequest(BaseModel):
    allowed_capabilities: list[str] = Field(default_factory=list)
    denied_capabilities: list[str] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)
    external_effects_allowed: bool = False
    risk_level: str = Field(default="low", pattern=r"^(low|medium|high|critical)$")
    budget: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def deny_wins_and_lists_are_consistent(self) -> "MissionAuthorizationRequest":
        denied = set(self.denied_capabilities)
        self.allowed_capabilities = [name for name in dict.fromkeys(self.allowed_capabilities) if name not in denied]
        self.denied_capabilities = list(dict.fromkeys(self.denied_capabilities))
        return self


class MissionResponse(BaseModel):
    id: str
    inception_id: str | None = None
    opportunity_id: str | None = None
    origin_type: str = "CREATOR_INCEPTION"
    creator_id: str
    title: str
    objective: str
    status: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    authorization_json: dict[str, Any]


class TaskResponse(BaseModel):
    id: str
    mission_id: str
    step_id: str
    universe_id: str
    agent_id: str
    status: str
    input_json: dict[str, Any]
    output_json: dict[str, Any]
    error_json: dict[str, Any]
    attempt_count: int
    max_attempts: int
    idempotency_key: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
