from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterWorker(Strict):
    worker_uuid: UUID
    worker_name: str = Field(..., min_length=1, max_length=128)
    version: str = Field(..., min_length=1, max_length=32)
    capabilities: list[str] = Field(default_factory=list, max_length=100)


class Heartbeat(Strict):
    version: str = Field(..., min_length=1, max_length=32)
    status: str = Field("available", pattern="^(available|busy)$")


class Claim(Strict):
    lease_seconds: int = Field(60, ge=1, le=3600)


class LeaseAction(Strict):
    dispatch_id: UUID
    lease_token: str = Field(..., min_length=20)


class FailAction(LeaseAction):
    error_code: str = Field(..., min_length=1, max_length=64)
    error_message: str = Field("", max_length=2000)


class WorkerView(BaseModel):
    id: str
    worker_uuid: str
    worker_name: str
    version: str
    capabilities: list[str]
    status: str
    last_heartbeat: datetime | None
    registered_at: datetime
    updated_at: datetime


class RegisteredWorker(WorkerView):
    worker_token: str


class ExecutionEnvelope(BaseModel):
    dispatch_id: str
    mission_id: str
    task_id: str
    agent_id: str | None
    capability: str
    priority: int
    lease_token: str
    attempt: int
    deadline: datetime
    metadata: dict
