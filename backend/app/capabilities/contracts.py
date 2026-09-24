from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class IdempotencyClass(StrEnum):
    SAFE = "SAFE"
    IDEMPOTENT = "IDEMPOTENT"
    AT_MOST_ONCE = "AT_MOST_ONCE"


class CapabilityIntent(BaseModel):
    capability: str = Field(..., min_length=1, max_length=128)
    action: str = Field(..., min_length=1, max_length=128)
    resource: str | None = Field(default=None, max_length=512)
    arguments: dict[str, Any] = Field(default_factory=dict)
    external_effect: bool = False
    idempotency_class: IdempotencyClass = IdempotencyClass.SAFE
    idempotency_key: str | None = Field(default=None, max_length=256)


class MissionAuthorization(BaseModel):
    allowed_capabilities: list[str] = Field(default_factory=list)
    denied_capabilities: list[str] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)
    external_effects_allowed: bool = False
    risk_level: str = "low"
    budget: dict[str, Any] = Field(default_factory=dict)
    expires_at: str | None = None
    version: int = Field(default=1, ge=1)
    authorized_by: str
    authorized_at: str


class CapabilityContext(BaseModel):
    """Who a capability is running for. An adapter needs this to keep Missions apart."""

    mission_id: str = Field(..., min_length=1)
    task_id: str | None = None
    authorization: MissionAuthorization


class CapabilityResult(BaseModel):
    capability: str
    action: str
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] = Field(default_factory=dict)
