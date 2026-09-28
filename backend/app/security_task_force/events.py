from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

EVENT_TYPES = frozenset({
    "mission.compiled.v1",
    "mission.authorized.v1",
    "mission.state_changed.v1",
    "mission.completed.v1",
    "mission.aborted.v1",
    "action.requested.v1",
    "action.decided.v1",
    "action.dispatched.v1",
    "action.executed.v1",
    "grant.issued.v1",
    "grant.revoked.v1",
    "evidence.recorded.v1",
    "finding.verified.v1",
    "killswitch.engaged.v1",
})
_VERSIONED = re.compile(r"^[a-z_]+\.[a-z_]+\.v[0-9]+$")


class STFEvent(BaseModel):
    schema_version: int = 1
    event_id: str = Field(min_length=1)
    event_type: str
    timestamp: datetime
    mission_id: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    causation_id: str | None = None
    payload: dict[str, Any]

    @field_validator("event_type")
    @classmethod
    def _known_and_versioned(cls, value: str) -> str:
        if _VERSIONED.fullmatch(value) is None:
            raise ValueError("event names carry an explicit .vN suffix")
        if value not in EVENT_TYPES:
            raise ValueError(f"unknown event type: {value}")
        return value


def event(event_type: str, mission_id: str, correlation_id: str, payload: dict[str, Any],
          causation_id: str | None = None, *, event_id: str | None = None) -> STFEvent:
    return STFEvent(
        event_id=event_id or str(uuid4()), event_type=event_type, timestamp=datetime.now(timezone.utc),
        mission_id=mission_id, correlation_id=correlation_id, causation_id=causation_id, payload=payload,
    )
