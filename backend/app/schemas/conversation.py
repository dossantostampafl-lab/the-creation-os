from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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
    content: str = Field(..., min_length=1, max_length=4000)
    client_message_id: str | None = Field(None, min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageResponse(BaseModel):
    message_id: str
    conversation_id: str
    route: str
    response: str
    inception: dict[str, str] | None = None
    system_state: dict[str, Any] | None = None
    correlation_id: str


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
