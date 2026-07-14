from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MissionDecisionResponse(BaseModel):
    id: str
    mission_id: str
    consolidation_id: str | None
    decision: str
    justification: dict[str, Any]
    consolidation_fingerprint: str | None
    created_at: datetime
    updated_at: datetime
