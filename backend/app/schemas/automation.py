from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AutomationExecuteRequest(BaseModel):
    connector_id: str = Field(min_length=1, max_length=128)
    capability: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = Field(gt=0, le=30)
    idempotency_key: str = Field(min_length=1, max_length=128)


class AutomationExecutionResponse(BaseModel):
    id: str
    creator_id: str
    connector_id: str
    capability: str
    idempotency_key: str
    request_fingerprint: str
    status: str
    result_payload: dict[str, Any]
    error_code: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime


class AutomationCapabilityResponse(BaseModel):
    connector_id: str
    capabilities: list[dict[str, Any]]
