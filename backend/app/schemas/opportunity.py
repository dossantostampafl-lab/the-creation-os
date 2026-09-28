from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OpportunityThesisCreate(BaseModel):
    creator_id: str = Field(..., min_length=36, max_length=36)
    proposed_value: str = Field(..., min_length=1, max_length=8000)
    target_payer: str = Field(..., min_length=1, max_length=4000)
    capture_path: str = Field(..., min_length=1, max_length=4000)
    estimated_cost: dict[str, Any] = Field(default_factory=dict)
    expected_value: dict[str, Any] = Field(default_factory=dict)
    max_downside: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(..., ge=0.0, le=1.0)
    falsification_conditions: list[str] = Field(..., min_length=1)
    evidence_refs: list[str] = Field(..., min_length=1)
