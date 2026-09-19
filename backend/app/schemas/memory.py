from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.memory.contracts import MemoryCandidate

MemoryTypeLiteral = Literal["EPISODIC", "SEMANTIC", "OPERATIONAL", "CREATOR"]


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


class MemoryCreateRequest(BaseModel):
    memory_type: MemoryTypeLiteral
    content: str = Field(min_length=1)
    source: str = Field(min_length=1, max_length=128)
    importance: int = Field(ge=1, le=10)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreatorMemoryResponse(BaseModel):
    id: str
    creator_id: str
    memory_type: str
    source: str
    content: str
    importance: int
    metadata: dict[str, Any]
    memory_fingerprint: str
    created_at: datetime


class MemorySearchResponse(BaseModel):
    items: list[CreatorMemoryResponse]
