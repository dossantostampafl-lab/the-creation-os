from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

MEMORY_POLICY_VERSION = "v1.4.0"


class MemoryType(StrEnum):
    EPISODIC = "EPISODIC"
    SEMANTIC = "SEMANTIC"
    OPERATIONAL = "OPERATIONAL"
    CREATOR = "CREATOR"


@dataclass(frozen=True)
class MemoryDocument:
    memory_type: MemoryType
    normalized_content: str
    context_payload: dict[str, Any]
    fingerprint: str


@dataclass(frozen=True)
class MemoryContextItem:
    id: str
    memory_type: str
    source: str
    content: str
    importance: int
    fingerprint: str
    relevance_score: int


def normalize_memory_text(value: str) -> str:
    without_accents = "".join(
        char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_accents.strip().casefold())


def memory_relevance_score(normalized_query: str, normalized_content: str, importance: int) -> int:
    if not normalized_query:
        return importance
    terms = [term for term in normalized_query.split(" ") if term]
    matches = sum(1 for term in terms if term in normalized_content)
    exact_bonus = 3 if normalized_query in normalized_content else 0
    return importance * 10 + matches * 4 + exact_bonus


def select_memory_context(
    memories: list[Any],
    *,
    query: str,
    limit: int,
) -> list[MemoryContextItem]:
    normalized_query = normalize_memory_text(query)
    ranked = sorted(
        (
            MemoryContextItem(
                id=item.id,
                memory_type=item.memory_type,
                source=item.source,
                content=item.content,
                importance=item.importance,
                fingerprint=item.memory_fingerprint,
                relevance_score=memory_relevance_score(normalized_query, item.normalized_content, item.importance),
            )
            for item in memories
        ),
        key=lambda item: (-item.relevance_score, item.memory_type, item.source, item.id),
    )
    return ranked[:limit]


def deterministic_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_memory_document(
    *,
    creator_id: str,
    memory_type: MemoryType | str,
    content: str,
    source: str,
    importance: int,
    metadata: dict[str, Any] | None = None,
) -> MemoryDocument:
    resolved_type = MemoryType(memory_type)
    normalized = normalize_memory_text(content)
    payload = {
        "schema_version": "1.0",
        "policy_version": MEMORY_POLICY_VERSION,
        "creator_id": creator_id,
        "memory_type": resolved_type.value,
        "normalized_content": normalized,
        "source": source.strip(),
        "importance": importance,
        "metadata": metadata or {},
    }
    return MemoryDocument(
        memory_type=resolved_type,
        normalized_content=normalized,
        context_payload=payload,
        fingerprint=deterministic_fingerprint(payload),
    )
