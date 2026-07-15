from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
MANIFESTATION_SCHEMA_VERSION = "1.0"


class ManifestationState(StrEnum):
    PENDING = "PENDING"
    MANIFESTED = "MANIFESTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ManifestationDocument:
    state: ManifestationState
    payload: dict[str, Any]
    audit_metadata: dict[str, Any]
    fingerprint: str


def _canonical(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def is_valid_fingerprint(value: str | None) -> bool:
    return isinstance(value, str) and FINGERPRINT_PATTERN.fullmatch(value) is not None


def build_manifestation(decision: Any) -> ManifestationDocument:
    payload = _canonical(
        {
            "schema_version": MANIFESTATION_SCHEMA_VERSION,
            "mission_id": decision.mission_id,
            "decision_id": decision.id,
            "decision": decision.decision,
            "decision_fingerprint": decision.consolidation_fingerprint,
            "manifestation_type": "internal_record",
        }
    )
    audit_metadata = _canonical(
        {
            "schema_version": MANIFESTATION_SCHEMA_VERSION,
            "source": "malkuth",
            "decision_id": decision.id,
            "mission_id": decision.mission_id,
            "validation": {
                "decision_exists": True,
                "decision_approved": decision.decision == "APPROVED",
                "fingerprint_valid": is_valid_fingerprint(decision.consolidation_fingerprint),
                "previous_manifestation_absent": True,
            },
        }
    )
    fingerprint_payload = _canonical(
        {
            "state": ManifestationState.MANIFESTED.value,
            "payload": payload,
            "audit_metadata": audit_metadata,
        }
    )
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return ManifestationDocument(
        state=ManifestationState.MANIFESTED,
        payload=payload,
        audit_metadata=audit_metadata,
        fingerprint=fingerprint,
    )
