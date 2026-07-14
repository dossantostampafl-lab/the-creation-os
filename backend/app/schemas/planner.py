from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskCreate(Strict):
    mission_id: UUID
    parent_task_id: UUID | None = None
    name: str = Field(..., min_length=1, max_length=256)
    description: str = Field(..., min_length=1, max_length=8000)
    required_capability: UUID
    priority: int = Field(0, ge=-1000, le=1000)
    retry_limit: int = Field(3, ge=0, le=100)
    timeout_seconds: int = Field(300, ge=1)
    estimated_duration: int | None = Field(None, ge=1)


class TaskPatch(Strict):
    name: str | None = Field(None, min_length=1, max_length=256)
    description: str | None = Field(None, min_length=1, max_length=8000)
    priority: int | None = Field(None, ge=-1000, le=1000)


class DependencyCreate(Strict):
    dependency_id: UUID


class PlannerRequest(Strict):
    mission_id: UUID
    required_capability: UUID


class TaskResponse(BaseModel):
    id: str
    mission_id: str
    parent_task_id: str | None
    name: str
    description: str
    required_capability: str
    priority: int
    state: str
    retry_limit: int
    retry_count: int
    timeout_seconds: int
    estimated_duration: int | None
    created_at: datetime
    updated_at: datetime


class GraphResponse(BaseModel):
    task: TaskResponse
    predecessors: list[TaskResponse]
    successors: list[TaskResponse]


class TopologyResponse(BaseModel):
    mission_id: str
    tasks: list[TaskResponse]
