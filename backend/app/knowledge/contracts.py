from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Scope(BaseModel):
    model_config = ConfigDict(frozen=True)
    creator_id: str
    project_id: str | None = None

class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=262144)
    kind: Literal["document", "decision", "preference", "result", "diagnostic", "derived_note"] = "document"
    source_type: Literal["manual", "message", "mission", "task", "diagnostic_observation", "diagnostic_incident"] = "manual"
    source_id: str | None = None
    epistemic_state: Literal["recorded", "verified", "hypothesis"] = "recorded"
    dependencies: list[str] = Field(default_factory=list, max_length=32)
    valid_until: datetime | None = None
    project_id: str | None = None

class Evidence(BaseModel):
    item_id: str
    revision_id: str
    title: str
    content: str
    kind: str
    epistemic_state: str
    source_type: str
    source_id: str | None
    observed_at: datetime
    valid_until: datetime | None = None

class Written(BaseModel):
    item_id: str
    revision_id: str

class RetrievalResult(BaseModel):
    status: Literal["ok", "empty", "timeout", "unavailable"]
    evidences: list[Evidence] = Field(default_factory=list)
    knowledge_epoch: int = 0
    elapsed_ms: float = 0
