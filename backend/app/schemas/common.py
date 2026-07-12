from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BaseResponse(BaseModel):
    correlation_id: str


class TimestampedModel(BaseModel):
    created_at: datetime
    updated_at: datetime | None = None


class MessageMetadata(BaseModel):
    client_message_id: str | None = None
    interface: str | None = None
    input_mode: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
