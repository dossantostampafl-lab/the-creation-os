from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MissionAuthorizationRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=256)
    scope: dict[str, Any] = Field(default_factory=dict)
    allowed_capabilities: list[str] = Field(default_factory=list)
    allowed_resources: list[str] = Field(default_factory=list)
    restrictions: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MissionAuthorizationCheckRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=256)
    action: str = Field(min_length=1, max_length=128)
    capability_id: str = Field(min_length=1, max_length=256)
    resource: str | None = Field(default=None, max_length=1024)
    reason: str | None = Field(default=None, max_length=2048)


class MissionAuthorizationResponse(BaseModel):
    id: str
    mission_id: str
    project_id: str
    creator_id: str
    status: str
    scope_json: dict[str, Any]
    allowed_capabilities_json: list[str]
    allowed_resources_json: list[str]
    restrictions_json: dict[str, Any]
    approved_at: datetime | None
    suspended_at: datetime | None
    revoked_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any]
