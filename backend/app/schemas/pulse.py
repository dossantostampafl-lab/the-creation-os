from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PulseResponse(BaseModel):
    status: str
    database: dict[str, Any]
    redis: dict[str, Any]
    redis_streams: dict[str, Any]
    chronicles_chain: dict[str, Any]
    active_universes: int
    active_agents: int
    running_missions: int
    pending_inceptions: int
    pending_tasks: int
    failed_tasks: int
    error_count: int
    timestamp: datetime
