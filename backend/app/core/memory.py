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


def normalize_memory_text(value: str) -> str:
    without_accents = "".join(
        char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_accents.strip().casefold())


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
