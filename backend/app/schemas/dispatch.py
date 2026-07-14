from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Enqueue(Strict):
    task_id: UUID
    priority: int = 0
    max_attempts: int = Field(3, ge=1, le=100)


class Lease(Strict):
    worker_id: str = Field(..., min_length=1, max_length=128)
    lease_seconds: int = Field(60, ge=1, le=3600)


class LeaseCommand(Strict):
    worker_id: str
    lease_token: str = Field(..., min_length=20)
    lease_seconds: int = Field(60, ge=1, le=3600)


class Failure(Strict):
    worker_id: str
    lease_token: str = Field(..., min_length=20)
    error_code: str = Field(..., max_length=64)
    error_message: str = Field("", max_length=2000)


class Item(BaseModel):
    id: str
    task_id: str
    mission_id: str
    agent_id: str | None
    capability_id: str | None
    state: str
    priority: int
    available_at: datetime
    lease_owner: str | None
    lease_expires_at: datetime | None
    attempt_count: int
    max_attempts: int
    last_error_code: str | None
    acknowledged_at: datetime | None
    cancelled_at: datetime | None
    dead_lettered_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class Leased(BaseModel):
    item: Item | None
    lease_token: str | None


class Attempt(BaseModel):
    id: str
    dispatch_item_id: str
    attempt_number: int
    event_type: str
    worker_id: str | None
    error_code: str | None
    error_message: str | None
    metadata_json: dict
    created_at: datetime
