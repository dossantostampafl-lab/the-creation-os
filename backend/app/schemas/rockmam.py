from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RockmamAssessmentResponse(BaseModel):
    id: str
    sophia_understanding_id: str
    conversation_id: str
    assessment_result: str
    assessment_payload: dict[str, Any]
    source_fingerprint: str
    assessment_fingerprint: str
    created_at: datetime
    assessed_at: datetime
