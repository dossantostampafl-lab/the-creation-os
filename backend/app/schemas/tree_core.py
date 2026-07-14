from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CapabilityCreateRequest(StrictRequest):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field("", max_length=2000)


class CapabilityResponse(BaseModel):
    id: str
    name: str
    description: str


class AgentCreateRequest(StrictRequest):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field("", max_length=4000)
    universe: str = Field(..., min_length=1, max_length=64)
    priority: int = Field(0, ge=-1000, le=1000)


class AgentUpdateRequest(StrictRequest):
    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = Field(None, max_length=4000)
    universe: str | None = Field(None, min_length=1, max_length=64)
    priority: int | None = Field(None, ge=-1000, le=1000)


class AgentCapabilityRequest(StrictRequest):
    capability_id: UUID


class AgentResponse(BaseModel):
    id: str
    name: str
    description: str
    universe: str
    capabilities: list[CapabilityResponse]
    priority: int
    status: str
    version: int
    heartbeat_at: datetime | None
    created_at: datetime
    updated_at: datetime
    enabled: bool


class TreeCoreMatchRequest(StrictRequest):
    mission_id: UUID
    required_capabilities: list[str] = Field(..., min_length=1)


class TreeCoreMatchResponse(BaseModel):
    mission_id: str
    agents: list[AgentResponse]
