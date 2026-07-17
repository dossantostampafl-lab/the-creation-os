from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.core.policy import POLICY_VERSION, build_decision_explanation


def complete_consolidation(mission_id: str):
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        mission_id=mission_id,
        status="complete",
        payload_json={"mission_id": mission_id, "task_count": 1},
        inconsistencies_json=[],
        completeness_json={
            "complete": True,
            "expected_tasks": 1,
            "consolidated_tasks": 1,
            "pending_tasks": 0,
        },
        fingerprint="a" * 64,
    )


def decision(mission_id: str, consolidation):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        mission_id=mission_id,
        consolidation_id=consolidation.id if consolidation is not None else None,
        decision="APPROVED",
        consolidation_fingerprint=consolidation.fingerprint if consolidation is not None else None,
        created_at=now,
        updated_at=now,
    )


def failed_codes(document) -> set[str]:
    return {item["code"] for item in document.rules_applied if item["passed"] is False}


def test_policy_explanation_is_successful_deterministic_and_technical_only():
    mission_id = str(uuid.uuid4())
    consolidation = complete_consolidation(mission_id)
    item = decision(mission_id, consolidation)

    first = build_decision_explanation(mission_id, item, consolidation, 1)
    second = build_decision_explanation(mission_id, item, consolidation, 1)

    assert first == second
    assert first.policy_version == POLICY_VERSION
    assert len(first.fingerprint) == 64
    assert first.consistency_summary["consistent"] is True
    assert first.completeness_summary["complete"] is True
    assert first.explanation_payload["technical_readiness"] is True
    assert first.explanation_payload["policy_scope"] == "technical_readiness_only"


def test_policy_explanation_reports_missing_consolidation():
    mission_id = str(uuid.uuid4())
    item = decision(mission_id, None)

    document = build_decision_explanation(mission_id, item, None, 1)

    assert document.explanation_payload["technical_readiness"] is False
    assert {
        "consolidation_exists",
        "consolidation_complete",
        "no_blocking_inconsistencies",
        "valid_fingerprint",
        "completeness_confirmed",
    } <= failed_codes(document)


def test_policy_explanation_reports_inconsistent_consolidation():
    mission_id = str(uuid.uuid4())
    consolidation = complete_consolidation(mission_id)
    consolidation.inconsistencies_json = [{"code": "blocking"}]
    item = decision(mission_id, consolidation)

    document = build_decision_explanation(mission_id, item, consolidation, 1)

    assert document.explanation_payload["technical_readiness"] is False
    assert "no_blocking_inconsistencies" in failed_codes(document)


def test_policy_explanation_reports_non_single_active_decision():
    mission_id = str(uuid.uuid4())
    consolidation = complete_consolidation(mission_id)
    item = decision(mission_id, consolidation)

    document = build_decision_explanation(mission_id, item, consolidation, 2)

    assert document.explanation_payload["technical_readiness"] is False
    assert "single_active_decision" in failed_codes(document)
