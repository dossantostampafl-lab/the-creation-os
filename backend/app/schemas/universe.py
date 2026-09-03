from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UniverseCreateRequest(BaseModel):
    code: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9_\-]+$")
    name: str = Field(..., min_length=2, max_length=128)


class UniverseResponse(BaseModel):
    id: str
    code: str
    name: str
    active: bool
    created_at: datetime


class AgentCreateRequest(BaseModel):
    code: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9_\-]+$")
    name: str = Field(..., min_length=2, max_length=128)
    universe_id: str = Field(..., min_length=36, max_length=36)
    capabilities: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    id: str
    code: str
    name: str
    universe_id: str
    active: bool
    capabilities_json: dict[str, Any]
    created_at: datetime
