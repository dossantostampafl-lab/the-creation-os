from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

from app.inference.contracts import InferenceRequest


_SPACE_RE = re.compile(r"\s+")


def normalize_query(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    return _SPACE_RE.sub(" ", normalized)


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def extract_last_user_query(request: InferenceRequest) -> str | None:
    for message in reversed(request.messages):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
    return None


def build_context_hash(request: InferenceRequest) -> str:
    explicit = request.metadata.get("cache_context_hash")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    messages = list(request.messages)
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("role") == "user":
            messages = messages[:index]
            break
    return stable_hash(messages)


def build_generation_profile_hash(request: InferenceRequest) -> str:
    explicit = request.metadata.get("generation_profile_hash")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    provider_independent = bool(request.metadata.get("cache_provider_independent", False))
    requirements = request.requirements.model_dump(mode="json")
    if provider_independent:
        requirements.pop("preferred_provider", None)
        requirements.pop("fallback_providers", None)
        requirements.pop("routing_strategy", None)
    system_messages = [
        message.get("content")
        for message in request.messages
        if message.get("role") == "system"
    ]
    return stable_hash(
        {
            "model": request.model,
            "requirements": requirements,
            "system_messages": system_messages,
            "generation_contract_version": request.metadata.get("generation_contract_version", "v1"),
        }
    )


def build_authorization_fingerprint(request: InferenceRequest) -> str:
    explicit = request.metadata.get("authorization_fingerprint")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    authorization = request.metadata.get("authorization")
    if authorization is None:
        return "none"
    return stable_hash(authorization)


def build_exact_key(*, normalized_query: str, context: dict[str, Any]) -> str:
    return stable_hash({"query": normalized_query, "context": context})
