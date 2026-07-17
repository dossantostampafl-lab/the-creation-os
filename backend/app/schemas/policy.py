from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MissionDecisionReasoningResponse(BaseModel):
    id: str
    decision_id: str
    policy_version: str
    evaluation_timestamp: datetime
    rules_applied: list[dict[str, Any]]
    consistency_summary: dict[str, Any]
    completeness_summary: dict[str, Any]
    explanation_payload: dict[str, Any]
    fingerprint: str
    created_at: datetime
    updated_at: datetime
