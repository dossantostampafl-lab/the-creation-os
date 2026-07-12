from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class InceptionCreateRequest(BaseModel):
    conversation_id: str = Field(..., min_length=36, max_length=36)
    source_message_id: str = Field(..., min_length=36, max_length=36)
    title: str = Field(..., min_length=3, max_length=256)
    description: str = Field(..., min_length=1, max_length=8000)


class InceptionResponse(BaseModel):
    id: str
    conversation_id: str
    title: str
    description: str
    status: str
    trinity_assessment: dict[str, Any]
    proposed_at: datetime
    decided_at: datetime | None
    decided_by: str | None
    decision_reason: str | None


class InceptionDecisionRequest(BaseModel):
    reason: str | None = None
