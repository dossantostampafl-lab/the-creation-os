from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SophiaUnderstandingResponse(BaseModel):
    id: str
    god_interaction_id: str
    conversation_id: str
    understanding_type: str
    understanding_payload: dict[str, Any]
    source_fingerprint: str
    understanding_fingerprint: str
    created_at: datetime
    understood_at: datetime
