from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.memory.contracts import MemoryCandidate


class MemoryUpsertRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=128)
    value: dict[str, Any] = Field(default_factory=dict)


class MemoryResponse(BaseModel):
    id: str
    scope_id: str
    key: str
    value: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ConsciousMemoryCreateRequest(MemoryCandidate):
    pass


class ConsciousMemoryResponse(BaseModel):
    id: str
    source_type: str
    source_id: str
    content: str
    metadata_json: dict[str, Any]
    embedding: list[float]
    created_at: datetime
