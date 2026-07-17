from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PerceptionSourceResponse(BaseModel):
    id: str
    name: str
    universe: str
    provider: str
    capability_name: str
    connector_name: str
    enabled: bool
    state: str
    schedule_interval_seconds: int
    minimum_interval_seconds: int
    last_started_at: datetime | None
    last_succeeded_at: datetime | None
    last_failed_at: datetime | None
    failure_count: int
    max_consecutive_failures: int
    next_run_at: datetime | None
    last_cursor: str | None
    created_at: datetime
    updated_at: datetime


class PerceptionRunResponse(BaseModel):
    id: str
    source_id: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
    observations_count: int
    opportunities_count: int
    attempts_count: int
    error_code: str | None
    error_message: str | None
    metadata_json: dict
    created_at: datetime


class PerceptionRunResult(BaseModel):
    source: PerceptionSourceResponse
    run: PerceptionRunResponse
    observations_count: int
    opportunities_count: int
    notifications_count: int


class NotificationResponse(BaseModel):
    id: str
    recipient_actor_id: str
    type: str
    title: str
    message: str
    opportunity_id: str | None
    priority_score: float | None
    status: str
    created_at: datetime
    read_at: datetime | None
    acknowledged_at: datetime | None


class SchedulerRunResponse(BaseModel):
    results: list[PerceptionRunResult] = Field(default_factory=list)
