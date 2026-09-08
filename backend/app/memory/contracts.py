from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class MemorySourceType(StrEnum):
    CONVERSATION = "conversation"
    MESSAGE = "message"
    INCEPTION = "inception"
    MISSION = "mission"
    TASK = "task"
    AGENT_EXECUTION = "agent_execution"
    CAPABILITY_INVOCATION = "capability_invocation"


_AUTHORITY_KEYS = {
    "authorized",
    "authorization",
    "authority",
    "permissions",
    "permission",
    "allowed_capabilities",
    "denied_capabilities",
    "creator_approval",
}


class MemoryCandidate(BaseModel):
    source_type: MemorySourceType
    source_id: str = Field(..., min_length=36, max_length=36)
    content: str = Field(..., min_length=1, max_length=8000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def reject_authority_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        found = {key.lower().replace("-", "_") for key in value} & _AUTHORITY_KEYS
        if found:
            raise ValueError("memory metadata cannot assert or modify authority")
        return value
