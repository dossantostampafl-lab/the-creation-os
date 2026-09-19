from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

POLICY_VERSION = "central-core-policy-v1"
FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


@dataclass(frozen=True)
class PolicyRuleResult:
    code: str
    passed: bool
    detail: str

    def as_dict(self) -> dict[str, str | bool]:
        return {"code": self.code, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DecisionExplanationDocument:
    policy_version: str
    rules_applied: list[dict[str, str | bool]]
    consistency_summary: dict[str, Any]
    completeness_summary: dict[str, Any]
    explanation_payload: dict[str, Any]
    fingerprint: str


def _canonical(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def _rule(code: str, passed: bool, detail: str) -> PolicyRuleResult:
    return PolicyRuleResult(code=code, passed=passed, detail=detail)


def build_decision_explanation(
    mission_id: str,
    decision: Any,
    consolidation: Any | None,
    active_decision_count: int,
) -> DecisionExplanationDocument:
    consolidation_exists = consolidation is not None
    consolidation_complete = bool(consolidation is not None and consolidation.status == "complete")
    no_blocking_inconsistencies = bool(consolidation is not None and not (consolidation.inconsistencies_json or []))
    valid_fingerprint = bool(
        consolidation is not None
        and isinstance(consolidation.fingerprint, str)
        and FINGERPRINT_PATTERN.fullmatch(consolidation.fingerprint) is not None
    )
    decision_immutable = bool(decision.created_at is not None and decision.updated_at is not None and decision.created_at == decision.updated_at)
    single_active_decision = active_decision_count == 1
    decision_matches_mission = decision.mission_id == mission_id
    decision_matches_consolidation = bool(
        decision.consolidation_id is None
        or (
            consolidation is not None
            and decision.consolidation_id == consolidation.id
            and decision.consolidation_fingerprint == consolidation.fingerprint
        )
    )

    completeness = consolidation.completeness_json if consolidation is not None else {}
    expected_tasks = completeness.get("expected_tasks")
    completeness_confirmed = bool(
        consolidation is not None
        and completeness.get("complete") is True
        and isinstance(expected_tasks, int)
        and expected_tasks > 0
        and completeness.get("consolidated_tasks") == expected_tasks
        and completeness.get("pending_tasks") == 0
    )

    rules = [
        _rule("consolidation_exists", consolidation_exists, "MissionDecision references available technical consolidation"),
        _rule("consolidation_complete", consolidation_complete, "MissionConsolidation status is complete"),
        _rule("no_blocking_inconsistencies", no_blocking_inconsistencies, "MissionConsolidation has no blocking inconsistencies"),
        _rule("valid_fingerprint", valid_fingerprint, "MissionConsolidation fingerprint is a valid SHA-256 hex digest"),
        _rule("decision_immutable", decision_immutable, "MissionDecision timestamps indicate no mutation after creation"),
        _rule("single_active_decision", single_active_decision, "Mission has exactly one MissionDecision"),
        _rule("decision_matches_mission", decision_matches_mission, "MissionDecision belongs to the evaluated Mission"),
        _rule(
            "decision_matches_consolidation",
            decision_matches_consolidation,
            "MissionDecision consolidation reference and fingerprint match the immutable consolidation",
        ),
        _rule("completeness_confirmed", completeness_confirmed, "MissionConsolidation completeness summary is technically complete"),
    ]
    ordered_rules = sorted((item.as_dict() for item in rules), key=lambda item: str(item["code"]))
    failed = [item["code"] for item in ordered_rules if item["passed"] is False]
    consistency_summary = _canonical(
        {
            "consistent": not failed,
            "failed_rules": failed,
            "active_decision_count": active_decision_count,
            "decision_id": decision.id,
            "consolidation_id": consolidation.id if consolidation is not None else None,
        }
    )
    completeness_summary = _canonical(
        {
            "complete": completeness_confirmed,
            "source": completeness,
        }
    )
    explanation_payload = _canonical(
        {
            "schema_version": "1.0",
            "mission_id": mission_id,
            "decision_id": decision.id,
            "decision": decision.decision,
            "technical_readiness": not failed,
            "rules_failed": failed,
            "policy_scope": "technical_readiness_only",
        }
    )
    fingerprint_payload = _canonical(
        {
            "policy_version": POLICY_VERSION,
            "rules_applied": ordered_rules,
            "consistency_summary": consistency_summary,
            "completeness_summary": completeness_summary,
            "explanation_payload": explanation_payload,
        }
    )
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return DecisionExplanationDocument(
        policy_version=POLICY_VERSION,
        rules_applied=ordered_rules,
        consistency_summary=consistency_summary,
        completeness_summary=completeness_summary,
        explanation_payload=explanation_payload,
        fingerprint=fingerprint,
    )
