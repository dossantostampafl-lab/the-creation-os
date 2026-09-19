from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


class DecisionState(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


@dataclass(frozen=True)
class DecisionDocument:
    decision: DecisionState
    justification: dict[str, Any]
    consolidation_fingerprint: str | None


def _reason(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


def evaluate_decision(mission_id: str, consolidation: Any | None) -> DecisionDocument:
    reasons: list[dict[str, str]] = []
    fingerprint: str | None = None

    if consolidation is None:
        reasons.append(_reason("consolidation_missing", "Tree Core consolidation is not available"))
    else:
        fingerprint = consolidation.fingerprint
        completeness = consolidation.completeness_json or {}
        inconsistencies = consolidation.inconsistencies_json or []
        payload = consolidation.payload_json or {}
        expected = completeness.get("expected_tasks")
        consolidated = completeness.get("consolidated_tasks")
        pending = completeness.get("pending_tasks")

        if consolidation.mission_id != mission_id:
            reasons.append(_reason("mission_mismatch", "Consolidation belongs to another Mission"))
        if consolidation.status != "complete":
            reasons.append(_reason("consolidation_not_complete", "Consolidation status is not complete"))
        if completeness.get("complete") is not True:
            reasons.append(_reason("completeness_not_confirmed", "Technical completeness is not confirmed"))
        if not isinstance(expected, int) or expected <= 0:
            reasons.append(_reason("expected_tasks_invalid", "Expected Task count must be positive"))
        if not isinstance(consolidated, int) or consolidated != expected:
            reasons.append(_reason("task_count_mismatch", "Consolidated Task count differs from expected count"))
        if pending != 0:
            reasons.append(_reason("pending_tasks", "One or more Tasks remain pending"))
        if inconsistencies:
            reasons.append(_reason("blocking_inconsistencies", "Consolidation contains blocking inconsistencies"))
        if not isinstance(fingerprint, str) or FINGERPRINT_PATTERN.fullmatch(fingerprint) is None:
            reasons.append(_reason("fingerprint_invalid", "Consolidation fingerprint is invalid"))
        if payload.get("mission_id") != mission_id:
            reasons.append(_reason("payload_mission_mismatch", "Consolidated payload belongs to another Mission"))
        if payload.get("task_count") != expected:
            reasons.append(_reason("payload_task_count_mismatch", "Payload Task count differs from completeness summary"))

    decision = DecisionState.REQUIRES_REVIEW if reasons else DecisionState.APPROVED
    ordered_reasons = sorted(reasons, key=lambda item: (item["code"], item["detail"]))
    return DecisionDocument(
        decision=decision,
        justification={
            "schema_version": "1.0",
            "technical_readiness": decision == DecisionState.APPROVED,
            "reasons": ordered_reasons,
        },
        consolidation_fingerprint=fingerprint,
    )
