from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.domain import Actor, AuthorizationDenied
from app.models.entities import Conversation, Inception, Message
from app.models.opportunity import Opportunity, OpportunityEvidence, OpportunityObservation
from app.services.capability_governance import CAPABILITY_DISABLED
from app.services.opportunities import (
    OBSERVATION_DUPLICATE,
    OBSERVATION_INVALID,
    OPPORTUNITY_EXPIRED,
    OPPORTUNITY_INCEPTION_ALREADY_CREATED,
    OPPORTUNITY_INVALID_TRANSITION,
    OPPORTUNITY_NOT_APPROVED,
    OpportunityDiscoveryService,
    OpportunityStatus,
)


class FakeGovernance:
    def __init__(self, denied: bool = False) -> None:
        self.denied = denied
        self.calls = 0

    async def authorize_execution(self, *args, **kwargs):
        self.calls += 1
        if self.denied:
            raise CAPABILITY_DISABLED("disabled")
        return object()


class FakeOpportunityRepository:
    def __init__(self) -> None:
        self.observation_items: dict[str, OpportunityObservation] = {}
        self.opportunity_items: dict[str, Opportunity] = {}
        self.evidence: list[OpportunityEvidence] = []
        self.conversations: dict[str, Conversation] = {}
        self.messages: dict[str, Message] = {}
        self.inceptions: dict[str, Inception] = {}
        self.events: list[tuple[str, str | None, dict]] = []
        self.commits = 0

    async def observation_by_fingerprint(self, fingerprint: str) -> OpportunityObservation | None:
        return next((item for item in self.observation_items.values() if item.observation_fingerprint == fingerprint), None)

    async def add_observation(self, item: OpportunityObservation) -> OpportunityObservation:
        item.id = item.id or str(uuid.uuid4())
        item.created_at = item.created_at or datetime.now(timezone.utc)
        self.observation_items[item.id] = item
        return item

    async def observations_for_discovery(self, enabled_universes: set[str]) -> list[OpportunityObservation]:
        return [item for item in self.observation_items.values() if item.universe in enabled_universes]

    async def observations(self, *, universe=None, limit=100, offset=0):
        items = [item for item in self.observation_items.values() if universe is None or item.universe == universe]
        return items[offset : offset + limit]

    async def opportunity_by_correlation(self, correlation_key: str) -> Opportunity | None:
        return next(
            (
                item
                for item in self.opportunity_items.values()
                if item.correlation_key == correlation_key and item.status in {"detected", "under_analysis", "pending_creator_review"}
            ),
            None,
        )

    async def add_opportunity(self, item: Opportunity) -> Opportunity:
        item.id = item.id or str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        item.created_at = item.created_at or now
        item.updated_at = item.updated_at or now
        self.opportunity_items[item.id] = item
        return item

    async def add_evidence(self, opportunity_id: str, observation_id: str) -> None:
        self.evidence.append(OpportunityEvidence(opportunity_id=opportunity_id, observation_id=observation_id))

    async def opportunities(self, *, universe=None, status=None, min_priority=None, limit=50, offset=0):
        items = list(self.opportunity_items.values())
        if universe:
            items = [item for item in items if item.universe == universe]
        if status:
            items = [item for item in items if item.status == status]
        if min_priority is not None:
            items = [item for item in items if item.priority_score >= min_priority]
        items.sort(key=lambda item: item.priority_score, reverse=True)
        return items[offset : offset + limit]

    async def opportunity(self, opportunity_id: str, *, lock: bool = False) -> Opportunity | None:
        return self.opportunity_items.get(opportunity_id)

    async def expirable(self, now: datetime):
        return [
            item
            for item in self.opportunity_items.values()
            if item.expires_at <= now and item.status in {"detected", "under_analysis", "pending_creator_review"}
        ]

    async def add_conversation(self, item: Conversation) -> Conversation:
        item.id = item.id or str(uuid.uuid4())
        self.conversations[item.id] = item
        return item

    async def add_message(self, item: Message) -> Message:
        item.id = item.id or str(uuid.uuid4())
        item.created_at = item.created_at or datetime.now(timezone.utc)
        self.messages[item.id] = item
        return item

    async def add_inception(self, item: Inception) -> Inception:
        item.id = item.id or str(uuid.uuid4())
        item.proposed_at = item.proposed_at or datetime.now(timezone.utc)
        self.inceptions[item.id] = item
        return item

    async def add_event(self, event_type: str, aggregate_id: str | None, actor_id: str, actor_role: str, correlation_id: str, payload: dict):
        self.events.append((event_type, aggregate_id, payload))

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None


def observation(**overrides):
    data = {
        "universe": "finance",
        "source": "fixture.market",
        "subject": "ACME",
        "event_type": "volume_anomaly",
        "title": "ACME volume anomaly",
        "summary": "Volume rose above threshold.",
        "source_reliability": 0.82,
        "correlation_key": "acme:volume",
        "normalized_data": {"volume_ratio": 2.7},
        "evidence": {"fixture": True},
    }
    data.update(overrides)
    return data


@pytest.fixture
def actor():
    return Actor("creator-1", "creator")


@pytest.fixture
def service():
    repo = FakeOpportunityRepository()
    return OpportunityDiscoveryService(repo, FakeGovernance()), repo


@pytest.mark.asyncio
async def test_valid_observation_is_ingested(service, actor):
    svc, repo = service

    item = await svc.ingest_observation(actor, observation(), "c")

    assert item.id in repo.observation_items
    assert repo.events[-1][0] == "observation.ingested"


@pytest.mark.asyncio
async def test_invalid_observation_is_rejected(service, actor):
    svc, _ = service

    with pytest.raises(OBSERVATION_INVALID):
        await svc.ingest_observation(actor, observation(title=""), "c")


@pytest.mark.asyncio
async def test_duplicate_observation_is_rejected(service, actor):
    svc, _ = service

    await svc.ingest_observation(actor, observation(), "c")

    with pytest.raises(OBSERVATION_DUPLICATE):
        await svc.ingest_observation(actor, observation(), "c")


@pytest.mark.asyncio
async def test_discovery_creates_ranked_opportunity_with_score(service, actor):
    svc, repo = service

    items = await svc.run_discovery(actor, [observation(), observation(event_type="volatility_increase", title="Volatility", summary="Volatility increased.")], "c")

    assert len(items) == 1
    item = items[0]
    assert item.status == OpportunityStatus.PENDING_CREATOR_REVIEW.value
    assert 0 <= item.priority_score <= 1
    assert item.scoring["weights"]["confidence"] == 0.35
    assert len(repo.evidence) == 2
    assert repo.events[-2][0] == "opportunity.detected"
    assert repo.events[-1][0] == "opportunity.review.requested"


@pytest.mark.asyncio
async def test_governance_denial_blocks_discovery_before_persistence(actor):
    repo = FakeOpportunityRepository()
    svc = OpportunityDiscoveryService(repo, FakeGovernance(denied=True))

    with pytest.raises(CAPABILITY_DISABLED):
        await svc.run_discovery(actor, [observation()], "c")

    assert repo.observation_items == {}
    assert repo.opportunity_items == {}


@pytest.mark.asyncio
async def test_approve_reject_and_invalid_transitions(service, actor):
    svc, _ = service
    item = (await svc.run_discovery(actor, [observation()], "c"))[0]

    approved = await svc.approve(actor, item.id, "yes", "c")

    assert approved.status == OpportunityStatus.APPROVED.value
    with pytest.raises(OPPORTUNITY_INVALID_TRANSITION):
        await svc.reject(actor, item.id, "late", "c")


@pytest.mark.asyncio
async def test_only_creator_can_review(service):
    svc, _ = service
    creator = Actor("creator-1", "creator")
    item = (await svc.run_discovery(creator, [observation()], "c"))[0]

    with pytest.raises(AuthorizationDenied):
        await svc.approve(Actor("agent-1", "agent"), item.id, "no", "c")


@pytest.mark.asyncio
async def test_expiration_blocks_review(service, actor):
    svc, _ = service
    item = (await svc.run_discovery(actor, [observation()], "c"))[0]
    item.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    expired = await svc.expire(actor, "c")

    assert expired[0].status == OpportunityStatus.EXPIRED.value
    with pytest.raises(OPPORTUNITY_EXPIRED):
        await svc.approve(actor, item.id, "late", "c")


@pytest.mark.asyncio
async def test_convert_requires_approval_and_prevents_duplicate_inception(service, actor):
    svc, repo = service
    item = (await svc.run_discovery(actor, [observation()], "c"))[0]

    with pytest.raises(OPPORTUNITY_NOT_APPROVED):
        await svc.convert_to_inception(actor, item.id, "c")

    await svc.approve(actor, item.id, "yes", "c")
    converted = await svc.convert_to_inception(actor, item.id, "c")

    assert converted.status == OpportunityStatus.CONVERTED_TO_INCEPTION.value
    assert converted.inception_id in repo.inceptions
    assert len(repo.inceptions) == 1
    with pytest.raises(OPPORTUNITY_INCEPTION_ALREADY_CREATED):
        await svc.convert_to_inception(actor, item.id, "c")
