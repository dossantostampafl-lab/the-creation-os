from __future__ import annotations

import re
from dataclasses import dataclass

from app.cache.contracts import CacheIntent, CacheSensitivity
from app.inference.contracts import InferenceRequest


_CACHEABLE = {
    CacheIntent.KNOWLEDGE_STATIC,
    CacheIntent.EXPLANATION,
    CacheIntent.DOCUMENT_QA,
    CacheIntent.DETERMINISTIC_COMPUTE,
}

_ACTION_RE = re.compile(
    r"^\s*(create|delete|remove|send|email|post|publish|update|modify|execute|run|activate|deactivate|"
    r"approve|reject|transfer|buy|sell|place|cancel|deploy|merge|write|save|upload)\b",
    re.IGNORECASE,
)
_LIVE_RE = re.compile(
    r"\b(now|right now|current|currently|today|latest|live|status|online|connected|available now)\b",
    re.IGNORECASE,
)
_FINANCIAL_RE = re.compile(
    r"\b(btc|bitcoin|eth|ethereum|sol|solana|stock|share|market|price|quote|portfolio|position|pnl|"
    r"probability|prediction market|order book|trade)\b",
    re.IGNORECASE,
)
_AUTH_RE = re.compile(
    r"\b(permission|authorized|authorization|allowed|access|role|credential|token)\b",
    re.IGNORECASE,
)
_SECURITY_RE = re.compile(
    r"\b(security decision|risk gate|policy decision|authentication decision|authorize this|safe to execute)\b",
    re.IGNORECASE,
)
_EXPLANATION_RE = re.compile(
    r"^\s*(explain|describe|define|what is|what are|how does|how do|how is|why does|why is|"
    r"explique|descreva|defina|o que é|o que são|como funciona|como funciona a|por que)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CachePolicyEvaluation:
    intent: CacheIntent
    sensitivity: CacheSensitivity
    eligible: bool
    reason: str


def _explicit_intent(request: InferenceRequest) -> CacheIntent | None:
    raw = request.metadata.get("cache_intent")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return CacheIntent(raw.strip().upper())
    except ValueError:
        return CacheIntent.UNKNOWN


def _sensitivity(request: InferenceRequest) -> CacheSensitivity:
    raw = request.metadata.get("cache_sensitivity", CacheSensitivity.PRIVATE.value)
    if not isinstance(raw, str):
        return CacheSensitivity.NO_CACHE
    try:
        return CacheSensitivity(raw.strip().upper())
    except ValueError:
        return CacheSensitivity.NO_CACHE


def classify_intent(request: InferenceRequest, query: str) -> CacheIntent:
    if request.metadata.get("cache_policy") == "bypass":
        return CacheIntent.UNKNOWN
    if (
        request.metadata.get("enable_capability_intents")
        or request.metadata.get("task_id")
        or request.metadata.get("mission_id")
        or str(request.metadata.get("tool_state_class", "read_only")) != "read_only"
    ):
        return CacheIntent.SYSTEM_COMMAND
    if _SECURITY_RE.search(query):
        return CacheIntent.SECURITY_DECISION
    if _AUTH_RE.search(query):
        return CacheIntent.AUTHORIZATION
    if _ACTION_RE.search(query):
        return CacheIntent.SYSTEM_COMMAND
    if _LIVE_RE.search(query):
        return CacheIntent.FINANCIAL_LIVE if _FINANCIAL_RE.search(query) else CacheIntent.LIVE_STATE
    explicit = _explicit_intent(request)
    if explicit is not None:
        return explicit
    if request.metadata.get("retrieval_fingerprint") or request.metadata.get("knowledge_version"):
        return CacheIntent.DOCUMENT_QA
    if _EXPLANATION_RE.search(query):
        return CacheIntent.EXPLANATION
    return CacheIntent.UNKNOWN


def evaluate_policy(request: InferenceRequest, query: str) -> CachePolicyEvaluation:
    sensitivity = _sensitivity(request)
    if request.metadata.get("cache_policy") == "bypass":
        return CachePolicyEvaluation(CacheIntent.UNKNOWN, sensitivity, False, "explicit_cache_bypass")
    if sensitivity in {CacheSensitivity.SENSITIVE, CacheSensitivity.NO_CACHE}:
        return CachePolicyEvaluation(CacheIntent.UNKNOWN, sensitivity, False, "sensitivity_disallows_cache")

    intent = classify_intent(request, query)
    if intent == CacheIntent.DOCUMENT_QA:
        if not request.metadata.get("retrieval_fingerprint") or not request.metadata.get("knowledge_version"):
            return CachePolicyEvaluation(intent, sensitivity, False, "document_qa_requires_versioned_retrieval")
    if intent not in _CACHEABLE:
        return CachePolicyEvaluation(intent, sensitivity, False, f"intent_{intent.value.lower()}_bypasses_cache")
    return CachePolicyEvaluation(intent, sensitivity, True, "cacheable_intent")


def ttl_seconds_for_intent(
    intent: CacheIntent,
    *,
    default_ttl: int,
    document_ttl: int,
    deterministic_ttl: int,
) -> int:
    if intent == CacheIntent.DOCUMENT_QA:
        return document_ttl
    if intent == CacheIntent.DETERMINISTIC_COMPUTE:
        return deterministic_ttl
    return default_ttl
