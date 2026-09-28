from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, model_validator


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
    # Correlation for Security Task Force events, read from the payload; None for every other event.
    mission_id: str | None = None
    action_id: str | None = None
    task_id: str | None = None
    environment_id: str | None = None
    evidence_sha256: str | None = None

    @model_validator(mode="after")
    def _correlate(self) -> "ChronicleResponse":
        for name in ("mission_id", "action_id", "task_id", "environment_id", "evidence_sha256"):
            value = self.payload_json.get(name) if isinstance(self.payload_json, dict) else None
            if getattr(self, name) is None and isinstance(value, str):
                setattr(self, name, value)
        return self


class ChronicleVerifyResponse(BaseModel):
    valid: bool
    message: str
