from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ProbeStatus = Literal["healthy", "unhealthy", "unknown"]


@dataclass(frozen=True)
class ProbeOutcome:
    value: bool | None
    safe_evidence: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ProbeResult:
    status: ProbeStatus
    latency_ms: int
    safe_evidence: dict[str, object] = field(default_factory=dict)

    @property
    def healthy(self) -> bool | None:
        if self.status == "healthy":
            return True
        if self.status == "unhealthy":
            return False
        return None


class Observation(BaseModel):
    id: str
    type: Literal["observation"] = "observation"
    resource: str = Field(min_length=1, max_length=128)
    rule: str = Field(min_length=1, max_length=128)
    status: ProbeStatus
    observed_at: datetime
    valid_until: datetime
    latency_ms: int | None = Field(default=None, ge=0)
    safe_evidence: dict[str, object] = Field(default_factory=dict)
    incident_episode_id: str | None = None
