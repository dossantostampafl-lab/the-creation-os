from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MissionCreateRequest(BaseModel):
    inception_id: str = Field(..., min_length=36, max_length=36)
    title: str = Field(..., min_length=3, max_length=256)
    objective: str = Field(..., min_length=1, max_length=8000)


class MissionPlanRequest(BaseModel):
    strategy: str = Field(..., min_length=1, max_length=12000)
    completion_criteria: dict[str, Any] = Field(default_factory=dict)


class MissionResponse(BaseModel):
    id: str
    inception_id: str
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
