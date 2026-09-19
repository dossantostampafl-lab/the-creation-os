from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExecutionCreate(Strict):
    dispatch_id: UUID
    lease_token: str = Field(..., min_length=20)
    handler_name: str = Field(..., min_length=1, max_length=128)
    handler_version: str = Field(..., min_length=1, max_length=32)


class ExecutionCommand(Strict):
    lease_token: str = Field(..., min_length=20)


class ExecutionView(BaseModel):
    id: str
    dispatch_item_id: str
    mission_id: str
    task_id: str
    agent_id: str
    worker_id: str
    capability_id: str
    attempt_number: int
    handler_name: str
    handler_version: str
    state: str
    deadline: datetime
    max_duration_seconds: int
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class ExecutionEventView(BaseModel):
    id: str
    execution_id: str
    sequence: int
    event_type: str
    actor_type: str
    actor_id: str
    metadata_json: dict
    created_at: datetime


class ExecutionResultView(BaseModel):
    execution_id: str
    mission_id: str
    task_id: str
    agent_id: str
    capability_id: str
    status: str
    output: dict | None
    metrics: dict | None
    warnings: list | None
    error_code: str | None
    started_at: datetime | None
    finished_at: datetime | None
