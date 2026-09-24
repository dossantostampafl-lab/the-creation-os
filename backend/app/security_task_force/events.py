from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel


class STFEvent(BaseModel):
    schema_version: int = 1
    event_id: str
    event_type: str
    timestamp: datetime
    mission_id: str
    correlation_id: str
    causation_id: str | None = None
    payload: dict[str, Any]


def event(event_type: str, mission_id: str, correlation_id: str, payload: dict[str, Any], causation_id: str | None = None) -> STFEvent:
    return STFEvent(event_id=str(uuid4()), event_type=event_type, timestamp=datetime.now(timezone.utc), mission_id=mission_id, correlation_id=correlation_id, causation_id=causation_id, payload=payload)
