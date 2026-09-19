from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MissionConsolidationResponse(BaseModel):
    id: str
    mission_id: str
    status: str
    payload: dict[str, Any]
    inconsistencies: list[dict[str, str]]
    completeness: dict[str, Any]
    fingerprint: str
    created_at: datetime
    updated_at: datetime
