"""Rotating the Creator's password, which had no supported way to happen.

The password lives in the environment, so the flow is: change CREATOR_BOOTSTRAP_PASSWORD,
restart, run the command. What matters is that the new password works, the old one stops
working, and the sessions opened under the old one are gone.
"""

from __future__ import annotations

import os
import uuid

import bcrypt
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.admin.creator as admin
from app.admin.creator import rotate_creator_password
from app.auth import token_store
from app.config import settings
from app.models.entities import Chronicle, Creator

pytestmark = pytest.mark.integration

OLD = "the-old-password"
NEW = "the-new-password"


@pytest.fixture
async def database(monkeypatch):
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text(
            "TRUNCATE chronicles, agent_executions, tasks, mission_steps, mission_plans, missions, "
            "inceptions, messages, conversations, agents, universes, creator RESTART IDENTITY CASCADE"
        ))
    monkeypatch.setattr(admin, "AsyncSessionLocal", factory)
    yield factory
    await engine.dispose()


async def add_creator(factory, username: str | None = None, password: str = OLD) -> str:
    creator = Creator(
        id=str(uuid.uuid4()),
        username=username or settings.creator_bootstrap_username,
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode("ascii"),
        is_active=True,
    )
    async with factory() as session:
        session.add(creator)
        await session.commit()
    return creator.id


async def stored_hash(factory) -> str:
    async with factory() as session:
        creator = await session.scalar(select(Creator))
        return creator.password_hash


@pytest.mark.asyncio
async def test_the_new_password_works_and_the_old_one_stops(database, monkeypatch) -> None:
    creator_id = await add_creator(database)
    monkeypatch.setattr(settings, "creator_bootstrap_password", type(settings.creator_bootstrap_password)(NEW))
    await token_store.register_refresh_token(creator_id, "a-token")

    assert await rotate_creator_password() == 0

    stored = (await stored_hash(database)).encode("ascii")
    assert bcrypt.checkpw(NEW.encode(), stored), "the new password must work"
    assert not bcrypt.checkpw(OLD.encode(), stored), "the old password must not"
    assert not await token_store.consume_refresh_token(creator_id, "a-token"), (
        "a session opened under the old password must not survive the rotation"
    )


@pytest.mark.asyncio
async def test_the_rotation_is_written_into_the_chronicle(database, monkeypatch) -> None:
    await add_creator(database)
    monkeypatch.setattr(settings, "creator_bootstrap_password", type(settings.creator_bootstrap_password)(NEW))

    await rotate_creator_password()

    async with database() as session:
        events = [item.event_type for item in (await session.scalars(select(Chronicle))).all()]
    assert events == ["creator_password_rotated"]


@pytest.mark.asyncio
async def test_running_it_without_changing_the_environment_is_refused(database, monkeypatch) -> None:
    """The usual mistake is running it before editing .env; that must not read as success."""
    await add_creator(database)
    monkeypatch.setattr(settings, "creator_bootstrap_password", type(settings.creator_bootstrap_password)(OLD))
    before = await stored_hash(database)

    assert await rotate_creator_password() == 3
    assert await stored_hash(database) == before


@pytest.mark.asyncio
async def test_it_refuses_a_creator_that_is_not_the_configured_one(database, monkeypatch) -> None:
    await add_creator(database, username="someone-else")
    monkeypatch.setattr(settings, "creator_bootstrap_password", type(settings.creator_bootstrap_password)(NEW))
    before = await stored_hash(database)

    assert await rotate_creator_password() == 1
    assert await stored_hash(database) == before


@pytest.mark.asyncio
async def test_it_refuses_when_there_is_no_creator(database, monkeypatch) -> None:
    monkeypatch.setattr(settings, "creator_bootstrap_password", type(settings.creator_bootstrap_password)(NEW))

    assert await rotate_creator_password() == 1
