from types import SimpleNamespace

import pytest

from app.core.domain import Actor
from app.security_task_force.service import StfService

RANGE = "cyber_range:lab-a"


class FakeRepository:
    def __init__(self, *, advances_executed: int):
        self.advances_executed = advances_executed
        self.recorded = []
        self.run = SimpleNamespace(
            id="run-1",
            creator_id="creator-1",
            mission_id="m1",
            mission_version=1,
            state="COMPLETED",
            desired_state="RUN",
            plan_json=[
                {
                    "action_id": "campaign-start",
                    "task_id": "t-start",
                    "capability": "range.campaign.start",
                    "target_id": "stf-foundation-v1",
                    "environment_id": RANGE,
                },
                {
                    "action_id": "advance-1",
                    "task_id": "t-a1",
                    "capability": "range.campaign.advance",
                    "target_id": "stf-foundation-v1",
                    "environment_id": RANGE,
                },
                {
                    "action_id": "advance-2",
                    "task_id": "t-a2",
                    "capability": "range.campaign.advance",
                    "target_id": "stf-foundation-v1",
                    "environment_id": RANGE,
                },
                {
                    "action_id": "observe",
                    "task_id": "t-observe",
                    "capability": "range.health.verify",
                    "target_id": "juice-shop",
                    "environment_id": RANGE,
                },
            ],
        )

    async def get_run(self, run_id, *, lock=False):
        return self.run if run_id == "run-1" else None

    async def get_qualification(self, run_id):
        return None

    async def get_dispatch(self, execution_id, run_id=None):
        if execution_id == "exec-observe":
            return SimpleNamespace(execution_id=execution_id, action_id="observe", status="executed")
        return None

    async def get_dispatch_for_action(self, run_id, action_id):
        if action_id == "campaign-start":
            return SimpleNamespace(action_id=action_id, status="executed")
        if action_id == "advance-1" and self.advances_executed >= 1:
            return SimpleNamespace(action_id=action_id, status="executed")
        if action_id == "advance-2" and self.advances_executed >= 2:
            return SimpleNamespace(action_id=action_id, status="executed")
        return None

    async def record_evidence(self, run_id, execution_id, record):
        self.recorded.append(record)

    async def project_verified_findings(self, run_id):
        return []


class FakeSession:
    pass


def service_with(advances_executed: int):
    service = StfService(FakeSession())
    service.repository = FakeRepository(advances_executed=advances_executed)
    return service


async def test_campaign_evidence_is_rejected_until_the_campaign_reaches_that_scenario():
    service = service_with(advances_executed=1)

    with pytest.raises(ValueError, match="campaign has not reached scenario"):
        await service.record_evidence(
            Actor("creator-1", "creator"),
            "m1",
            "run-1",
            "exec-observe",
            scenario_id="blue-detection-baseline",
            kind="attack",
            source="range-red",
            payload={"observed": True},
        )

    assert service.repository.recorded == []


async def test_campaign_evidence_is_accepted_after_required_advances_are_proven():
    service = service_with(advances_executed=2)

    record = await service.record_evidence(
        Actor("creator-1", "creator"),
        "m1",
        "run-1",
        "exec-observe",
        scenario_id="blue-detection-baseline",
        kind="attack",
        source="range-red",
        payload={"observed": True},
    )

    assert record.payload["_scenario_id"] == "blue-detection-baseline"
    assert len(service.repository.recorded) == 1
