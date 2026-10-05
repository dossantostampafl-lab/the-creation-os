from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from test_services import FakeRepository

from app.api import living_core
from app.api.dependencies import actor as actor_dependency
from app.core.domain import Actor, InceptionStatus, InvalidOrigin, MissionStatus
from app.main import app
from app.models.entities import Chronicle, Creator, Message, Mission, Task
from app.repositories.domain import DomainRepository
from app.services.domain import LivingCoreService


class MessageRepository(FakeRepository):
    async def creator_message_by_client_id(self, conversation_id, actor_id, client_message_id):
        return next((item for (kind, _), item in self.entities.items()
                     if kind is Message and item.conversation_id == conversation_id and item.actor_id == actor_id
                     and item.role == 'creator' and item.metadata_json.get('client_message_id') == client_message_id), None)


@pytest.fixture
async def message_client():
    actor = Actor(str(uuid.uuid4()), 'creator')
    repo = MessageRepository()
    service = LivingCoreService(repo)
    conversation = await service.create_conversation(actor, 'Source idempotency', str(uuid.uuid4()))
    app.dependency_overrides[actor_dependency] = lambda: actor
    app.dependency_overrides[living_core.service] = lambda: service
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            yield client, conversation.id, repo
    finally:
        app.dependency_overrides.pop(actor_dependency, None)
        app.dependency_overrides.pop(living_core.service, None)


@pytest.mark.asyncio
async def test_source_endpoint_replays_same_message_and_emits_one_event(message_client):
    client, conversation_id, repo = message_client
    body = {'content': 'Explicit manual mission', 'client_message_id': str(uuid.uuid4()), 'metadata': {'channel': 'manual'}}
    first = await client.post(f'/api/v1/conversations/{conversation_id}/messages', json=body)
    replay = await client.post(f'/api/v1/conversations/{conversation_id}/messages', json=body)
    assert first.status_code == replay.status_code == 201
    assert first.json()['id'] == replay.json()['id']
    assert first.json()['role'] == 'creator'
    assert first.json()['metadata_json']['client_message_id'] == body['client_message_id']
    assert len([entity for (kind, _), entity in repo.entities.items() if kind is Message]) == 1
    assert len([event for event in repo.events if event['event_type'] == 'conversation_message_added']) == 1


@pytest.mark.asyncio
async def test_source_endpoint_conflicting_content_returns_409_without_another_message(message_client):
    client, conversation_id, repo = message_client
    key = str(uuid.uuid4())
    first = await client.post(f'/api/v1/conversations/{conversation_id}/messages', json={'content': 'Original objective', 'client_message_id': key})
    conflict = await client.post(f'/api/v1/conversations/{conversation_id}/messages', json={'content': 'Different objective', 'client_message_id': key})
    assert first.status_code == 201
    assert conflict.status_code == 409
    assert len([entity for (kind, _), entity in repo.entities.items() if kind is Message]) == 1


@pytest.mark.asyncio
async def test_source_endpoint_accepts_request_id_as_idempotency_key(message_client):
    client, conversation_id, _ = message_client
    body = {'content': 'Same intention', 'request_id': str(uuid.uuid4())}
    first = await client.post(f'/api/v1/conversations/{conversation_id}/messages', json=body)
    replay = await client.post(f'/api/v1/conversations/{conversation_id}/messages', json=body)
    assert first.status_code == replay.status_code == 201
    assert first.json()['id'] == replay.json()['id']


@pytest.mark.asyncio
@pytest.mark.integration
async def test_concurrent_source_retries_create_one_message_and_one_chronicle(stf_db):
    _, factory = stf_db
    creator_id, key = str(uuid.uuid4()), str(uuid.uuid4())
    actor = Actor(creator_id, 'creator')
    async with factory() as session:
        session.add(Creator(id=creator_id, username=f'source-{creator_id}', password_hash='unused', is_active=True))
        await session.commit()
        conversation = await LivingCoreService(DomainRepository(session)).create_conversation(actor, 'Concurrent source', str(uuid.uuid4()))
        conversation_id = conversation.id

    async def send():
        async with factory() as session:
            message = await LivingCoreService(DomainRepository(session)).add_message(
                actor, conversation_id, 'One stable mission objective', {}, str(uuid.uuid4()), client_message_id=key,
            )
            return message.id

    # Each request has an independent transaction; PostgreSQL's Conversation lock must serialize them.
    ids = await asyncio.gather(*(send() for _ in range(8)))
    assert len(set(ids)) == 1
    assert await send() == ids[0]  # A new session also recovers a committed response after it was lost.
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Message).where(Message.conversation_id == conversation_id)) == 1
        assert await session.scalar(select(func.count()).select_from(Chronicle).where(
            Chronicle.aggregate_id == conversation_id, Chronicle.event_type == 'conversation_message_added')) == 1
        with pytest.raises(InvalidOrigin, match='different content'):
            await LivingCoreService(DomainRepository(session)).add_message(
                actor, conversation_id, 'Changed objective', {}, str(uuid.uuid4()), client_message_id=key,
            )
        await session.rollback()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize('unavailable', ['missing_agent', 'inactive_agent', 'other_universe_agent', 'inactive_universe', 'available'])
@pytest.mark.parametrize('entrypoint', ['start', 'authorize'])
async def test_authorization_requires_an_active_agent_in_the_selected_universe(stf_db, unavailable, entrypoint):
    _, factory = stf_db
    creator_id = str(uuid.uuid4())
    actor, cid = Actor(creator_id, 'creator'), str(uuid.uuid4())
    universe_code = f'target_{uuid.uuid4().hex}'
    async with factory() as session:
        session.add(Creator(id=creator_id, username=f'readiness-{creator_id}', password_hash='unused', is_active=True))
        await session.commit()
        service = LivingCoreService(DomainRepository(session))
        conversation = await service.create_conversation(actor, 'Readiness', cid)
        source = await service.add_message(actor, conversation.id, 'Explicit mission', {}, cid)
        inception = await service.create_inception(actor, conversation.id, source.id, 'Readiness', 'Bounded objective', cid)
        await service.transition_inception(actor, inception.id, InceptionStatus.AWAITING_CREATOR_DECISION, cid)
        await service.transition_inception(actor, inception.id, InceptionStatus.APPROVED, cid)
        mission = await service.create_mission(actor, inception.id, 'Readiness', 'Bounded objective', cid)
        universe = await service.create_universe(actor, universe_code, 'Target', cid)
        await service.set_universe_active(actor, universe.id, unavailable != 'inactive_universe', cid)
        if unavailable != 'missing_agent':
            agent_universe = universe
            if unavailable == 'other_universe_agent':
                agent_universe = await service.create_universe(actor, f'other_{uuid.uuid4().hex}', 'Other', cid)
                await service.set_universe_active(actor, agent_universe.id, True, cid)
            agent = await service.create_agent(actor, f'agent_{uuid.uuid4().hex}', 'Agent', agent_universe.id, {}, cid)
            if unavailable == 'inactive_agent':
                await service.set_agent_active(actor, agent.id, False, cid)
        await service.transition_mission(actor, mission.id, MissionStatus.PLANNED, cid, {
            'strategy': 'Bounded manual plan',
            'steps': [{'step_key': 'one', 'title': 'One', 'description': 'One task', 'universe': universe_code, 'position': 1}],
        })
        await service.transition_mission(actor, mission.id, MissionStatus.VALIDATED, cid)
        mission_id = mission.id
        async def authorize_or_start():
            if entrypoint == 'start':
                return await service.start_mission(actor, mission_id, cid)
            return await service.transition_mission(actor, mission_id, MissionStatus.AUTHORIZED, cid)
        if unavailable == 'available':
            await authorize_or_start()
        else:
            with pytest.raises(InvalidOrigin):
                await authorize_or_start()
        await session.rollback()
    async with factory() as session:
        persisted = await session.get(Mission, mission_id)
        expected_status = ('executing' if entrypoint == 'start' else 'authorized') if unavailable == 'available' else 'validated'
        assert persisted.status == expected_status
        assert bool(persisted.authorization_json) == (unavailable == 'available')
        assert await session.scalar(select(func.count()).select_from(Task).where(Task.mission_id == mission_id)) == (1 if unavailable == 'available' and entrypoint == 'start' else 0)
        assert await session.scalar(select(func.count()).select_from(Chronicle).where(
            Chronicle.aggregate_id == mission_id, Chronicle.event_type == 'mission_authorized')) == (1 if unavailable == 'available' else 0)
