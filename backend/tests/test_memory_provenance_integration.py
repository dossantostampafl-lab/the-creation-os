from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.entities import ConsciousMemory, Conversation, Creator

pytestmark = pytest.mark.integration


@pytest.fixture
async def database():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text(
            "TRUNCATE conscious_memory, conversations, creator RESTART IDENTITY CASCADE"
        ))
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_conscious_memory_requires_existing_source(database):
    async with database() as session:
        session.add(ConsciousMemory(
            source_type="mission",
            source_id=str(uuid.uuid4()),
            content="orphan memory",
            metadata_json={},
            embedding=[0.0] * 8,
        ))
        with pytest.raises(DBAPIError, match="provenance source does not exist"):
            await session.commit()


@pytest.mark.asyncio
async def test_conscious_memory_accepts_real_source_and_rejects_authority_metadata(database):
    creator_id = str(uuid.uuid4())
    conversation_id = str(uuid.uuid4())
    async with database() as session:
        session.add(Creator(id=creator_id, username="creator", password_hash="unused", is_active=True))
        await session.flush()
        session.add(Conversation(id=conversation_id, creator_id=creator_id, title="Source", status="active"))
        await session.commit()

    async with database() as session:
        session.add(ConsciousMemory(
            source_type="conversation",
            source_id=conversation_id,
            content="valid memory",
            metadata_json={"kind": "observation"},
            embedding=[0.0] * 8,
        ))
        await session.commit()

    async with database() as session:
        session.add(ConsciousMemory(
            source_type="conversation",
            source_id=conversation_id,
            content="authority escalation",
            metadata_json={"authorized": True},
            embedding=[0.0] * 8,
        ))
        with pytest.raises(DBAPIError, match="cannot assert authority"):
            await session.commit()
