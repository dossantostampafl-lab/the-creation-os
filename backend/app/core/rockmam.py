from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.models.sophia import SophiaUnderstanding

ROCKMAM_ASSESSMENT_VERSION = "v0.9.0"
FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


class RockmamResult(StrEnum):
    VIABLE = "VIABLE"
    NOT_VIABLE = "NOT_VIABLE"
    REQUIRES_CREATOR = "REQUIRES_CREATOR"


@dataclass(frozen=True)
class RockmamAssessmentDocument:
    result: RockmamResult
    payload: dict[str, Any]
    source_fingerprint: str
    fingerprint: str


def deterministic_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def valid_fingerprint(value: str | None) -> bool:
    return isinstance(value, str) and FINGERPRINT_PATTERN.match(value) is not None


def required_payload_complete(payload: dict[str, Any]) -> bool:
    return all(
        key in payload
        for key in (
            "god_interaction_id",
            "conversation_id",
            "interaction_type",
            "understanding_type",
            "normalized_message",
            "boundaries",
            "signals",
        )
    )


def boundaries_are_non_operational(payload: dict[str, Any]) -> bool:
    boundaries = payload.get("boundaries", {})
    return all(
        boundaries.get(key) is False
        for key in ("decides", "manifests", "executes", "creates_inception", "creates_mission")
    )


def build_assessment(understanding: SophiaUnderstanding) -> RockmamAssessmentDocument:
    payload = understanding.understanding_payload
    blockers: list[dict[str, str]] = []
    complete = required_payload_complete(payload)
    non_operational = boundaries_are_non_operational(payload)
    source_valid = valid_fingerprint(understanding.understanding_fingerprint)

    if not complete:
        blockers.append({"code": "understanding_incomplete", "severity": "blocking"})
    if not non_operational:
        blockers.append({"code": "understanding_boundary_violation", "severity": "blocking"})
    if not source_valid:
        blockers.append({"code": "invalid_understanding_fingerprint", "severity": "blocking"})
    if understanding.understanding_type == "UNSUPPORTED_UNDERSTANDING":
        blockers.append({"code": "unsupported_understanding", "severity": "blocking"})

    if blockers:
        result = RockmamResult.NOT_VIABLE
    elif understanding.understanding_type == "POTENTIAL_UNDERSTANDING":
        result = RockmamResult.REQUIRES_CREATOR
    else:
        result = RockmamResult.VIABLE

    source_fingerprint = deterministic_fingerprint(
        {
            "sophia_understanding_id": understanding.id,
            "understanding_fingerprint": understanding.understanding_fingerprint,
            "source_fingerprint": understanding.source_fingerprint,
            "understanding_type": understanding.understanding_type,
        }
    )
    assessment_payload = {
        "schema_version": "1.0",
        "assessment_version": ROCKMAM_ASSESSMENT_VERSION,
        "source": "SOPHIA",
        "sophia_understanding_id": understanding.id,
        "conversation_id": understanding.conversation_id,
        "result": result.value,
        "technical_viability": result != RockmamResult.NOT_VIABLE,
        "consistency": {
            "non_operational_boundaries": non_operational,
            "source_fingerprint_valid": source_valid,
        },
        "completeness": {
            "complete": complete,
            "required_fields": [
                "god_interaction_id",
                "conversation_id",
                "interaction_type",
                "understanding_type",
                "normalized_message",
                "boundaries",
                "signals",
            ],
        },
        "capabilities": {
            "internal_assessment_available": True,
            "external_execution_available": False,
            "requires_creator_direction": result == RockmamResult.REQUIRES_CREATOR,
        },
        "blockers": blockers,
    }
    fingerprint = deterministic_fingerprint(
        {
            "schema_version": "1.0",
            "assessment_version": ROCKMAM_ASSESSMENT_VERSION,
            "source_fingerprint": source_fingerprint,
            "payload": assessment_payload,
        }
    )
    return RockmamAssessmentDocument(
        result=result,
        payload=assessment_payload,
        source_fingerprint=source_fingerprint,
        fingerprint=fingerprint,
    )
