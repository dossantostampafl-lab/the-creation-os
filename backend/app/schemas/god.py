from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class GodConversationRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    idempotency_key: str = Field(..., min_length=1, max_length=128)


class GodConversationResponse(BaseModel):
    id: str
    conversation_id: str
    message_id: str
    god_message_id: str
    interaction_type: str
    reply: dict[str, Any]
    potential_detected: bool
    next_action: str
    fingerprint: str
    created_at: datetime
    completed_at: datetime
