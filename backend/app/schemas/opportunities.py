from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ObservationCreateRequest(BaseModel):
    universe: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1, max_length=128)
    subject: str = Field(min_length=1, max_length=256)
    event_type: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=256)
    summary: str = Field(min_length=1)
    observed_at: datetime | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)
    normalized_data: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    source_reliability: float = Field(ge=0, le=1)
    correlation_key: str | None = Field(default=None, max_length=256)
    external_id: str | None = Field(default=None, max_length=256)


class ObservationResponse(BaseModel):
    id: str
    universe: str
    source: str
    subject: str
    event_type: str
    title: str
    summary: str
    observed_at: datetime
    normalized_data: dict[str, Any]
    evidence: dict[str, Any]
    source_reliability: float
    correlation_key: str
    external_id: str | None
    created_at: datetime


class OpportunityResponse(BaseModel):
    id: str
    title: str
    universe: str
    category: str
    status: str
    summary: str
    explanation: str
    confidence: float
    impact: float
    urgency: float
    risk: float
    priority_score: float
    recommended_action: str
    evidence: dict[str, Any]
    risks: dict[str, Any]
    scoring: dict[str, Any]
    detected_at: datetime
    expires_at: datetime
    reviewed_at: datetime | None
    reviewed_by: str | None
    rejection_reason: str | None
    inception_id: str | None
    created_at: datetime
    updated_at: datetime


class DiscoveryRunRequest(BaseModel):
    observations: list[ObservationCreateRequest] = Field(default_factory=list)


class DiscoveryRunResponse(BaseModel):
    opportunities: list[OpportunityResponse]


class OpportunityReviewRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2048)
