from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CacheMode(StrEnum):
    OFF = "off"
    SHADOW = "shadow"
    EXACT = "exact"
    SEMANTIC = "semantic"


class CacheDecisionType(StrEnum):
    HIT = "HIT"
    MISS = "MISS"
    BYPASS = "BYPASS"
    REVALIDATE = "REVALIDATE"
    INVALIDATE = "INVALIDATE"


class CacheIntent(StrEnum):
    KNOWLEDGE_STATIC = "KNOWLEDGE_STATIC"
    EXPLANATION = "EXPLANATION"
    DOCUMENT_QA = "DOCUMENT_QA"
    DETERMINISTIC_COMPUTE = "DETERMINISTIC_COMPUTE"
    LIVE_STATE = "LIVE_STATE"
    FINANCIAL_LIVE = "FINANCIAL_LIVE"
    SYSTEM_COMMAND = "SYSTEM_COMMAND"
    EXTERNAL_WRITE = "EXTERNAL_WRITE"
    AUTHORIZATION = "AUTHORIZATION"
    SECURITY_DECISION = "SECURITY_DECISION"
    TRANSACTION = "TRANSACTION"
    TIME_SENSITIVE = "TIME_SENSITIVE"
    UNKNOWN = "UNKNOWN"


class CacheSensitivity(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    PRIVATE = "PRIVATE"
    SENSITIVE = "SENSITIVE"
    NO_CACHE = "NO_CACHE"


class CacheContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    creator_scope: str
    universe_scope: str | None = None
    intent: CacheIntent
    sensitivity: CacheSensitivity = CacheSensitivity.PRIVATE
    context_hash: str
    context_version: str | None = None
    knowledge_version: str | None = None
    retrieval_fingerprint: str | None = None
    generation_profile_hash: str
    policy_version: str
    authorization_fingerprint: str
    tool_state_class: str = "read_only"
    tags: tuple[str, ...] = ()


class CachedResponsePayload(BaseModel):
    provider: str
    model: str
    content: str
    finish_reason: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CacheDecision(BaseModel):
    decision: CacheDecisionType
    reason: str
    cache_entry_id: str | None = None
    semantic_similarity: float | None = None
    intent_match: bool = True
    scope_match: bool = True
    context_match: bool = True
    freshness: str = "UNKNOWN"
    knowledge_version_match: bool = True


class CacheLookupResult(BaseModel):
    decision: CacheDecision
    exact_key: str | None = None
    query: str | None = None
    normalized_query: str | None = None
    context: CacheContext | None = None
    response: CachedResponsePayload | None = None
    shadow_candidate: CachedResponsePayload | None = None
    shadow_candidate_id: str | None = None
    lock_token: str | None = None
    embedding: list[float] | None = None
    lookup_started_at: datetime | None = None
