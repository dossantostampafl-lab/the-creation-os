import uuid
from datetime import datetime, timezone

import pytest

from app.core.domain import Actor, InceptionStatus, InvalidOrigin, MissionStatus
from app.models.entities import Conversation, Inception, Message, Mission
from app.services.domain import LivingCoreService


class FakeRepository:
    def __init__(self):
        self.entities = {}
        self.events = []
        self.commits = 0

    async def add(self, entity):
        if getattr(entity, "id", None) is None:
            entity.id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        for field in ("created_at", "updated_at", "proposed_at"):
            if hasattr(entity, field) and getattr(entity, field, None) is None:
                setattr(entity, field, now)
        self.entities[(type(entity), entity.id)] = entity
        return entity

    async def get(self, model, entity_id):
        return self.entities.get((model, entity_id))

    async def get_for_update(self, model, entity_id):
        return await self.get(model, entity_id)

    async def list_for_creator(self, model, creator_id):
        return [x for (kind, _), x in self.entities.items() if kind is model and getattr(x, "creator_id", None) == creator_id]

    async def source_message(self, conversation_id, message_id):
        item = self.entities.get((Message, message_id))
        return item if item and item.conversation_id == conversation_id else None

    async def mission_for_inception(self, inception_id, lock=False):
        return next((item for (kind, _), item in self.entities.items()
                     if kind is Mission and item.inception_id == inception_id), None)

    async def owner_id(self, model, entity_id):
        item = self.entities.get((model, entity_id))
        if item is None:
            return None
        if hasattr(item, "creator_id"):
            return item.creator_id
        conversation = self.entities.get((Conversation, item.conversation_id))
        return conversation.creator_id if conversation else None

    async def add_event(self, event_type, aggregate_type, aggregate_id, actor_id, actor_role, correlation_id, payload=None):
        event = {"event_id": str(uuid.uuid4()), "event_type": event_type, "aggregate_type": aggregate_type,
                 "aggregate_id": aggregate_id, "actor_id": actor_id, "actor_role": actor_role,
                 "correlation_id": correlation_id, "payload": payload or {}, "created_at": datetime.now(timezone.utc)}
        self.events.append(event)
        return event

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


@pytest.fixture
def actor():
    return Actor(str(uuid.uuid4()), "creator")


@pytest.fixture
def correlation_id():
    return str(uuid.uuid4())


@pytest.fixture
def repo():
    return FakeRepository()


@pytest.mark.asyncio
async def test_conversation_message_does_not_create_mission(repo, actor, correlation_id):
    service = LivingCoreService(repo)
    conversation = await service.create_conversation(actor, "Direct dialogue", correlation_id)
    await service.add_message(actor, conversation.id, "Just a conversation", {}, correlation_id)
    assert not any(kind is Mission for kind, _ in repo.entities)
    assert [e["event_type"] for e in repo.events] == ["conversation_created", "conversation_message_added"]


@pytest.mark.asyncio
async def test_inception_requires_valid_message_origin(repo, actor, correlation_id):
    service = LivingCoreService(repo)
    conversation = await service.create_conversation(actor, "Origin", correlation_id)
    with pytest.raises(InvalidOrigin):
        await service.create_inception(actor, conversation.id, str(uuid.uuid4()), "Intent", "Description", correlation_id)


async def approved_inception(repo, actor, correlation_id):
    service = LivingCoreService(repo)
    conversation = await service.create_conversation(actor, "Origin", correlation_id)
    message = await service.add_message(actor, conversation.id, "Explicit intent", {}, correlation_id)
    inception = await service.create_inception(actor, conversation.id, message.id, "Intent", "Description", correlation_id)
    await service.transition_inception(actor, inception.id, InceptionStatus.AWAITING_CREATOR_DECISION, correlation_id)
    await service.transition_inception(actor, inception.id, InceptionStatus.APPROVED, correlation_id)
    return service, inception


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [InceptionStatus.PROPOSED, InceptionStatus.AWAITING_CREATOR_DECISION, InceptionStatus.REJECTED])
async def test_mission_cannot_be_created_without_approved_inception(repo, actor, correlation_id, status):
    conversation = Conversation(id=str(uuid.uuid4()), creator_id=actor.id, title="Origin", status="active")
    inception = Inception(id=str(uuid.uuid4()), conversation_id=conversation.id, source_message_id=str(uuid.uuid4()),
                          title="Intent", description="Description", status=status.value, trinity_assessment_json={})
    inception.conversation = conversation
    repo.entities[(Conversation, conversation.id)] = conversation
    repo.entities[(Inception, inception.id)] = inception
    with pytest.raises(InvalidOrigin):
        await LivingCoreService(repo).create_mission(actor, inception.id, "Mission", "Objective", correlation_id)


@pytest.mark.asyncio
async def test_critical_events_contain_actor_timestamp_correlation_and_action(repo, actor, correlation_id):
    service, inception = await approved_inception(repo, actor, correlation_id)
    mission = await service.create_mission(actor, inception.id, "Mission", "Objective", correlation_id)
    await service.transition_mission(actor, mission.id, MissionStatus.PLANNED, correlation_id,
                                     {"strategy": "Safe plan", "completion_criteria": {"done": True}})
    await service.transition_mission(actor, mission.id, MissionStatus.VALIDATED, correlation_id)
    await service.transition_mission(actor, mission.id, MissionStatus.AUTHORIZED, correlation_id)
    for event in repo.events:
        assert event["actor_id"] == actor.id
        assert event["actor_role"] == "creator"
        assert event["correlation_id"] == correlation_id
        assert event["event_type"]
        assert event["created_at"].tzinfo is not None
    assert mission.authorization_json["authorized_by"] == actor.id


@pytest.mark.asyncio
async def test_chronicle_records_relevant_events(repo, actor, correlation_id):
    service, inception = await approved_inception(repo, actor, correlation_id)
    mission = await service.create_mission(actor, inception.id, "Mission", "Objective", correlation_id)
    await service.transition_mission(actor, mission.id, MissionStatus.CANCELLED, correlation_id)
    names = {event["event_type"] for event in repo.events}
    assert {"conversation_created", "conversation_message_added", "inception_created", "inception_submitted",
            "inception_approved", "mission_created", "mission_cancelled"} <= names
