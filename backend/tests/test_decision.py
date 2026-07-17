from __future__ import annotations

import copy
import uuid
from types import SimpleNamespace

import pytest

from app.core.decision import DecisionState, evaluate_decision
from app.services.decision import DecisionService
from app.services.domain import NotFoundError


def complete_consolidation(mission_id: str | None = None):
    mission_id = mission_id or str(uuid.uuid4())
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        mission_id=mission_id,
        status="complete",
        payload_json={"mission_id": mission_id, "task_count": 2, "tasks": [{"task_id": "a"}, {"task_id": "b"}]},
        inconsistencies_json=[],
        completeness_json={
            "complete": True,
            "expected_tasks": 2,
            "consolidated_tasks": 2,
            "pending_tasks": 0,
        },
        fingerprint="a" * 64,
    )


def reason_codes(document) -> set[str]:
    return {item["code"] for item in document.justification["reasons"]}


def test_complete_consolidation_is_technically_approved():
    consolidation = complete_consolidation()
    document = evaluate_decision(consolidation.mission_id, consolidation)
    assert document.decision == DecisionState.APPROVED
    assert document.justification == {"schema_version": "1.0", "technical_readiness": True, "reasons": []}
    assert document.consolidation_fingerprint == consolidation.fingerprint


def test_missing_consolidation_requires_review():
    document = evaluate_decision(str(uuid.uuid4()), None)
    assert document.decision == DecisionState.REQUIRES_REVIEW
    assert reason_codes(document) == {"consolidation_missing"}
    assert document.consolidation_fingerprint is None


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda item: setattr(item, "status", "incomplete"), "consolidation_not_complete"),
        (lambda item: item.completeness_json.update(complete=False), "completeness_not_confirmed"),
        (lambda item: item.completeness_json.update(expected_tasks=0), "expected_tasks_invalid"),
        (lambda item: item.completeness_json.update(consolidated_tasks=1), "task_count_mismatch"),
        (lambda item: item.completeness_json.update(pending_tasks=1), "pending_tasks"),
        (lambda item: item.inconsistencies_json.append({"code": "x"}), "blocking_inconsistencies"),
        (lambda item: setattr(item, "fingerprint", "invalid"), "fingerprint_invalid"),
        (lambda item: setattr(item, "mission_id", str(uuid.uuid4())), "mission_mismatch"),
        (lambda item: item.payload_json.update(mission_id=str(uuid.uuid4())), "payload_mission_mismatch"),
        (lambda item: item.payload_json.update(task_count=1), "payload_task_count_mismatch"),
    ],
)
def test_technical_readiness_failures_require_review(mutation, code):
    mission_id = str(uuid.uuid4())
    consolidation = complete_consolidation(mission_id)
    mutation(consolidation)
    document = evaluate_decision(mission_id, consolidation)
    assert document.decision == DecisionState.REQUIRES_REVIEW
    assert document.justification["technical_readiness"] is False
    assert code in reason_codes(document)


def test_decision_is_deterministic_and_does_not_mutate_consolidation():
    consolidation = complete_consolidation()
    consolidation.inconsistencies_json = [{"code": "z"}, {"code": "a"}]
    before = copy.deepcopy(vars(consolidation))
    first = evaluate_decision(consolidation.mission_id, consolidation)
    second = evaluate_decision(consolidation.mission_id, consolidation)
    assert first == second
    assert vars(consolidation) == before
    assert first.decision != DecisionState.REJECTED


class MissingMissionRepository:
    rolled_back = False

    async def mission(self, mission_id, lock=False):
        return None

    async def rollback(self):
        self.rolled_back = True


@pytest.mark.asyncio
async def test_missing_mission_rolls_back_and_raises_not_found():
    repository = MissingMissionRepository()
    with pytest.raises(NotFoundError, match="Mission not found"):
        await DecisionService(repository).decide(str(uuid.uuid4()))
    assert repository.rolled_back
