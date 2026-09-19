from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.domain import Actor
from app.models.opportunity import Opportunity, OpportunityObservation
from app.models.perception import CreatorNotification, PerceptionRun, PerceptionSource
from app.services.opportunities import OBSERVATION_DUPLICATE, OpportunityStatus
from app.services.perception import (
    NOTIFICATION_INVALID_TRANSITION,
    PERCEPTION_SOURCE_DISABLED,
    NotificationStatus,
    PerceptionService,
)


class FakeGovernance:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def authorize_execution(self, actor, *, connector_id, connector_capability, correlation_id):
        self.calls.append(connector_capability)
        return object()


class FakeAutomation:
    def __init__(self, observations: list[dict] | None = None) -> None:
        self.calls = 0
        self.observations = observations or [
            {
                "universe": "finance",
                "source": "fixture.market",
                "subject": "ACME",
                "event_type": "abnormal_volume",
                "title": "ACME abnormal volume",
                "summary": "Volume rose above the configured threshold.",
                "source_reliability": 0.84,
                "correlation_key": "acme:market",
                "normalized_data": {"volume_ratio": 3.1},
                "external_id": "acme-1",
            }
        ]

    async def execute(self, *args, **kwargs):
        self.calls += 1
        execution = type(
            "Execution",
            (),
            {"status": "succeeded", "result_payload": {"observations": self.observations}, "error_code": None},
        )()
        return execution, True


class FakeDiscovery:
    def __init__(self) -> None:
        self.fingerprints: set[str] = set()
        self.ingested = 0
        self.detected = 0
        now = datetime.now(timezone.utc)
        self.opportunity = Opportunity(
            id=str(uuid.uuid4()),
            title="ACME opportunity signal",
            universe="finance",
            category="informational_financial_investigation",
            status=OpportunityStatus.PENDING_CREATOR_REVIEW.value,
            summary="Signal detected.",
            explanation="Deterministic explanation.",
            confidence=0.82,
            impact=0.8,
            urgency=0.72,
            risk=0.2,
            source_reliability=0.84,
            priority_score=0.78,
            recommended_action="Investigate.",
            evidence={"observations": []},
            risks={"items": []},
            scoring={"final_score": 0.78},
            correlation_key="acme:market",
            detected_at=now,
            expires_at=now + timedelta(hours=1),
            created_at=now,
            updated_at=now,
        )

    async def _ingest_without_commit(self, actor, payload, correlation_id):
        key = payload.get("external_id") or payload["correlation_key"]
        if key in self.fingerprints:
            raise OBSERVATION_DUPLICATE("duplicate")
        self.fingerprints.add(key)
        self.ingested += 1
        return OpportunityObservation(
            id=str(uuid.uuid4()),
            universe=payload["universe"],
            source=payload["source"],
            subject=payload["subject"],
            event_type=payload["event_type"],
            title=payload["title"],
            summary=payload["summary"],
            observed_at=datetime.now(timezone.utc),
            normalized_data=payload.get("normalized_data") or {},
            evidence=payload.get("evidence") or {},
            source_reliability=payload["source_reliability"],
            correlation_key=payload["correlation_key"],
            external_id=payload.get("external_id"),
            observation_fingerprint=key,
            created_at=datetime.now(timezone.utc),
        )

    async def detect(self, actor, correlation_id):
        self.detected += 1
        return [self.opportunity]


class FakePerceptionRepository:
    def __init__(self, source: PerceptionSource | None = None, discovery: FakeDiscovery | None = None) -> None:
        self.session = None
        self.source_item = source or source_fixture()
        self.run_items: dict[str, PerceptionRun] = {}
        self.notification_items: dict[str, CreatorNotification] = {}
        self.events: list[str] = []
        self.commits = 0
        self.discovery = discovery or FakeDiscovery()

    async def source_by_name(self, name):
        return self.source_item if self.source_item.name == name else None

    async def source(self, source_id, *, lock=False):
        return self.source_item if self.source_item.id == source_id else None

    async def sources(self, *, universe=None):
        return [self.source_item]

    async def active_run(self, source_id):
        return next((item for item in self.run_items.values() if item.source_id == source_id and item.status == "running"), None)

    async def runs(self, source_id, *, limit=50):
        return [item for item in self.run_items.values() if item.source_id == source_id][:limit]

    async def add_run(self, item):
        item.id = item.id or str(uuid.uuid4())
        item.created_at = item.created_at or datetime.now(timezone.utc)
        self.run_items[item.id] = item
        return item

    async def add_source(self, item):
        self.source_item = item
        return item

    async def add_notification(self, item):
        item.id = item.id or str(uuid.uuid4())
        item.created_at = item.created_at or datetime.now(timezone.utc)
        self.notification_items[item.id] = item
        return item

    async def notification(self, notification_id, *, lock=False):
        return self.notification_items.get(notification_id)

    async def recent_notification(self, actor_id, opportunity_id, since):
        return next((item for item in self.notification_items.values() if item.recipient_actor_id == actor_id and item.opportunity_id == opportunity_id and item.created_at >= since), None)

    async def notifications(self, actor_id, *, status=None, limit=50, offset=0):
        items = [item for item in self.notification_items.values() if item.recipient_actor_id == actor_id and (status is None or item.status == status)]
        return items[offset : offset + limit]

    async def opportunities_for_notification(self):
        return [self.discovery.opportunity]

    async def add_event(self, event_type, aggregate_type, aggregate_id, actor_id, actor_role, correlation_id, payload):
        self.events.append(event_type)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None


def source_fixture(**overrides):
    now = datetime.now(timezone.utc)
    data = {
        "id": str(uuid.uuid4()),
        "name": "fixture-source",
        "universe": "finance",
        "provider": "fixture_finance",
        "capability_name": "collect_observations",
        "connector_name": "opportunity",
        "enabled": True,
        "schedule_interval_seconds": 900,
        "minimum_interval_seconds": 1,
        "failure_count": 0,
        "max_consecutive_failures": 3,
        "config_json": {},
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    return PerceptionSource(**data)


@pytest.fixture
def actor():
    return Actor("creator-1", "creator")


@pytest.mark.asyncio
async def test_valid_collection_persists_discovers_and_notifies(actor):
    discovery = FakeDiscovery()
    repo = FakePerceptionRepository(discovery=discovery)
    governance = FakeGovernance()
    service = PerceptionService(repo, automation=FakeAutomation(), discovery=discovery, governance=governance)

    result = await service.run_source(actor, repo.source_item.id, "c", force=True)

    assert result.observations_count == 1
    assert result.opportunities_count == 1
    assert result.notifications_count == 1
    assert repo.source_item.last_cursor is not None
    assert repo.source_item.failure_count == 0
    assert "perception.collection.succeeded" in repo.events
    assert "creator.notification.created" in repo.events
    assert "perception_source_collect" in governance.calls
    assert discovery.ingested == 1


@pytest.mark.asyncio
async def test_disabled_source_does_not_collect(actor):
    repo = FakePerceptionRepository(source_fixture(enabled=False))
    automation = FakeAutomation()
    service = PerceptionService(repo, automation=automation, discovery=FakeDiscovery(), governance=FakeGovernance())

    with pytest.raises(PERCEPTION_SOURCE_DISABLED):
        await service.run_source(actor, repo.source_item.id, "c", force=True)

    assert automation.calls == 0
    assert "opportunity.execution.denied" in repo.events


@pytest.mark.asyncio
async def test_duplicate_observation_is_ignored_without_duplicate_opportunity(actor):
    discovery = FakeDiscovery()
    repo = FakePerceptionRepository(discovery=discovery)
    service = PerceptionService(repo, automation=FakeAutomation(), discovery=discovery, governance=FakeGovernance())

    first = await service.run_source(actor, repo.source_item.id, "c1", force=True)
    second = await service.run_source(actor, repo.source_item.id, "c2", force=True)

    assert first.observations_count == 1
    assert second.observations_count == 0
    assert "observation.duplicate_ignored" in repo.events


@pytest.mark.asyncio
async def test_notification_read_and_acknowledge(actor):
    repo = FakePerceptionRepository()
    service = PerceptionService(repo, automation=FakeAutomation(), discovery=repo.discovery, governance=FakeGovernance())
    await service.run_source(actor, repo.source_item.id, "c", force=True)
    notification = next(iter(repo.notification_items.values()))

    read = await service.mark_notification_read(actor, notification.id, "c")
    acknowledged = await service.acknowledge_notification(actor, notification.id, "c")

    assert read.read_at is not None
    assert acknowledged.status == NotificationStatus.ACKNOWLEDGED.value
    with pytest.raises(NOTIFICATION_INVALID_TRANSITION):
        await service.mark_notification_read(actor, notification.id, "c")
