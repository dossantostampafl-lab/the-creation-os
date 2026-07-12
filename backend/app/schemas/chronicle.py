from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ChronicleResponse(BaseModel):
    id: str
    event_id: str
    correlation_id: str
    causation_id: str | None
    actor_type: str
    actor_id: str | None
    event_type: str
    aggregate_type: str
    aggregate_id: str | None
    payload_json: dict[str, Any]
    payload_hash: str
    previous_hash: str | None
    created_at: datetime


class ChronicleVerifyResponse(BaseModel):
    valid: bool
    message: str
