from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.domain import Actor, InceptionStatus, InvalidOrigin, InvalidStateTransition, MissionStatus
from app.models.entities import Chronicle, Conversation, Creator, Inception, Message, Mission
from app.repositories.domain import DomainRepository
from app.services.domain import LivingCoreService

pytestmark = pytest.mark.integration
DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture
async def database():
    engine = create_async_engine(DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE chronicles, mission_plans, missions, inceptions, messages, conversations, creator RESTART IDENTITY CASCADE"))
    yield factory
    await engine.dispose()


@pytest.fixture
async def creator(database):
    creator_id = str(uuid.uuid4())
    async with database() as session:
        session.add(Creator(id=creator_id, username="creator", password_hash="unused", is_active=True))
        await session.commit()
    return Actor(creator_id, "creator")


async def build_approved(service, actor, correlation_id):
    conversation = await service.create_conversation(actor, "PostgreSQL integration", correlation_id)
    message = await service.add_message(actor, conversation.id, "Explicit intention", {"channel": "test"}, correlation_id)
    inception = await service.create_inception(actor, conversation.id, message.id, "Intent", "Manifest safely", correlation_id)
    await service.transition_inception(actor, inception.id, InceptionStatus.AWAITING_CREATOR_DECISION, correlation_id)
    await service.transition_inception(actor, inception.id, InceptionStatus.APPROVED, correlation_id, "approved")
    return conversation, message, inception


@pytest.mark.asyncio
async def test_complete_persistence_flow_and_session_restart(database, creator):
    cid = str(uuid.uuid4())
    async with database() as session:
        service = LivingCoreService(DomainRepository(session))
        conversation, message, inception = await build_approved(service, creator, cid)
        mission = await service.create_mission(creator, inception.id, "Mission", "Objective", cid)
        await service.transition_mission(creator, mission.id, MissionStatus.PLANNED, cid,
                                         {"strategy": "central plan", "completion_criteria": {"done": True}})
        await service.transition_mission(creator, mission.id, MissionStatus.VALIDATED, cid)
        await service.transition_mission(creator, mission.id, MissionStatus.AUTHORIZED, cid)
        await service.close_conversation(creator, conversation.id, cid)
        await service.archive_conversation(creator, conversation.id, cid)
        ids = conversation.id, message.id, inception.id, mission.id
    async with database() as session:
        conversation = await session.get(Conversation, ids[0])
        message = await session.get(Message, ids[1])
        inception = await session.get(Inception, ids[2])
        mission = await session.get(Mission, ids[3])
        events = list((await session.scalars(select(Chronicle).order_by(Chronicle.position))).all())
        assert (conversation.status, inception.status, mission.status) == ("archived", "approved", "authorized")
        assert message.correlation_id == cid
        assert conversation.created_at.tzinfo is not None
        assert all(event.correlation_id == cid and event.created_at.tzinfo is not None for event in events)
        assert [event.position for event in events] == list(range(1, len(events) + 1))
        assert (await DomainRepository(session).verify_chronicle()).valid


@pytest.mark.asyncio
async def test_foreign_keys_unique_origin_and_state_constraints(database, creator):
    async with database() as session:
        session.add(Mission(id=str(uuid.uuid4()), creator_id=creator.id, inception_id=str(uuid.uuid4()),
                            title="bad", objective="bad", status="drafted", authorization_json={}))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
        session.add(Conversation(id=str(uuid.uuid4()), creator_id=creator.id, title="bad", status="arbitrary"))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_rollback_when_chronicle_write_fails(database, creator):
    class BrokenChronicleRepository(DomainRepository):
        async def add_event(self, *args, **kwargs):
            raise RuntimeError("chronicle unavailable")

    async with database() as session:
        service = LivingCoreService(BrokenChronicleRepository(session))
        with pytest.raises(RuntimeError):
            await service.create_conversation(creator, "must rollback", str(uuid.uuid4()))
        await session.rollback()
    async with database() as session:
        assert await session.scalar(select(Conversation)) is None
        assert await session.scalar(select(Chronicle)) is None


@pytest.mark.asyncio
async def test_inception_cancel_cascades_pre_authorized_mission_atomically(database, creator):
    cid = str(uuid.uuid4())
    async with database() as session:
        service = LivingCoreService(DomainRepository(session))
        _, _, inception = await build_approved(service, creator, cid)
        mission = await service.create_mission(creator, inception.id, "Mission", "Objective", cid)
        await service.transition_mission(creator, mission.id, MissionStatus.PLANNED, cid,
                                         {"strategy": "plan", "completion_criteria": {}})
        await service.transition_inception(creator, inception.id, InceptionStatus.CANCELLED, cid, "withdrawn")
        assert inception.status == mission.status == "cancelled"
    async with database() as session:
        event_types = set((await session.scalars(select(Chronicle.event_type))).all())
        assert {"inception_cancelled", "mission_cancelled"} <= event_types


@pytest.mark.asyncio
async def test_authorized_mission_blocks_inception_cancel(database, creator):
    cid = str(uuid.uuid4())
    async with database() as session:
        service = LivingCoreService(DomainRepository(session))
        _, _, inception = await build_approved(service, creator, cid)
        mission = await service.create_mission(creator, inception.id, "Mission", "Objective", cid)
        await service.transition_mission(creator, mission.id, MissionStatus.PLANNED, cid, {"strategy": "p"})
        await service.transition_mission(creator, mission.id, MissionStatus.VALIDATED, cid)
        await service.transition_mission(creator, mission.id, MissionStatus.AUTHORIZED, cid)
        with pytest.raises(InvalidOrigin):
            await service.transition_inception(creator, inception.id, InceptionStatus.CANCELLED, cid)
        await session.rollback()


@pytest.mark.asyncio
async def test_concurrent_approve_reject_has_single_winner(database, creator):
    cid = str(uuid.uuid4())
    async with database() as session:
        service = LivingCoreService(DomainRepository(session))
        conversation = await service.create_conversation(creator, "Concurrent", cid)
        message = await service.add_message(creator, conversation.id, "Intent", {}, cid)
        inception = await service.create_inception(creator, conversation.id, message.id, "Intent", "Description", cid)
        await service.transition_inception(creator, inception.id, InceptionStatus.AWAITING_CREATOR_DECISION, cid)
        inception_id = inception.id

    async def decide(target):
        async with database() as session:
            try:
                await LivingCoreService(DomainRepository(session)).transition_inception(creator, inception_id, target, cid)
                return "ok"
            except InvalidStateTransition:
                await session.rollback()
                return "rejected"

    results = await asyncio.gather(decide(InceptionStatus.APPROVED), decide(InceptionStatus.REJECTED))
    assert sorted(results) == ["ok", "rejected"]


@pytest.mark.asyncio
async def test_concurrent_chronicle_appends_are_linear(database, creator):
    async def create(index):
        async with database() as session:
            await LivingCoreService(DomainRepository(session)).create_conversation(
                creator, f"Concurrent {index}", str(uuid.uuid4()))
    await asyncio.gather(*(create(index) for index in range(6)))
    async with database() as session:
        events = list((await session.scalars(select(Chronicle).order_by(Chronicle.position))).all())
        assert [event.position for event in events] == list(range(1, 7))
        assert (await DomainRepository(session).verify_chronicle()).valid


@pytest.mark.asyncio
async def test_chronicle_verifier_detects_tampering(database, creator):
    async with database() as session:
        await LivingCoreService(DomainRepository(session)).create_conversation(
            creator, "Tamper target", str(uuid.uuid4()))
    async with database() as session:
        event = await session.scalar(select(Chronicle))
        event.payload_json = {"tampered": True}
        await session.commit()
    async with database() as session:
        result = await DomainRepository(session).verify_chronicle()
        assert not result.valid
        assert result.first_invalid_event_id is not None
        assert result.reason == "invalid event hash"
