from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MissionManifestationResponse(BaseModel):
    id: str
    mission_id: str
    decision_id: str
    manifestation_state: str
    manifestation_payload: dict[str, Any]
    manifestation_fingerprint: str
    audit_metadata: dict[str, Any]
    created_at: datetime
    manifested_at: datetime | None
