from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ConversationCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=128)


class ConversationResponse(BaseModel):
    id: str
    creator_id: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime


class MessageRequest(BaseModel):
    request_id: UUID | None = None
    content: str = Field(..., min_length=1, max_length=4000)
    client_message_id: str | None = Field(None, min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator('content')
    @classmethod
    def bound_utf8(cls, value: str) -> str:
        if len(json.dumps(value, ensure_ascii=False).encode()) > 8192:
            raise ValueError('content must not exceed8192 serialized UTF-8 bytes')
        return value


class MessageResponse(BaseModel):
    message_id: str
    conversation_id: str
    route: str
    response: str
    inception: dict[str, str] | None = None
    system_state: dict[str, Any] | None = None
    correlation_id: str
    # Which provider produced the reply, and, when a reserve answered, which one failed and why.
    provider: str | None = None
    fallback_from: str | None = None
    fallback_reason: str | None = None


class ConversationMessageResponse(BaseModel):
    id: str
    conversation_id: str
    actor_id: str
    role: str
    content: str
    route: str
    metadata_json: dict[str, Any]
    correlation_id: str
    created_at: datetime
