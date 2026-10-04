from __future__ import annotations

import uuid

import pytest
from stf_database import stf_db  # noqa: F401

from app.models.entities import Conversation, Creator
from app.services.deus_turns import TurnConflict, TurnStore


async def _conversation(factory):
    creator_id = str(uuid.uuid4())
    conversation_id = str(uuid.uuid4())
    async with factory() as session:
        session.add(Creator(id=creator_id, username=f"creator-{creator_id[:8]}", password_hash="x", is_active=True))
        # Flush the FK parent before inserting Conversation. The production schema has a
        # real creator_id foreign key and this fixture deliberately uses no ORM relationship.
        await session.flush()
        session.add(Conversation(id=conversation_id, creator_id=creator_id, title="retry", status="active"))
        await session.commit()
    return creator_id, conversation_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_clean_failed_turn_can_reclaim_same_request_id(stf_db):  # noqa: F811
    _, factory = stf_db
    creator_id, conversation_id = await _conversation(factory)
    store = TurnStore(factory)
    request_id = str(uuid.uuid4())

    first = await store.claim(creator_id, conversation_id, request_id, "Olá")
    await store.finish(first, None, "failed")

    second = await store.claim(creator_id, conversation_id, request_id, "Olá")
    assert second.id == first.id
    assert second.owner != first.owner
    assert second.state == "pending"
    assert await store.renew(second) is True

    payload = {"response": "Estou aqui."}
    await store.finish(second, payload, "completed")
    replay = await store.claim(creator_id, conversation_id, request_id, "Olá")
    assert replay.response == payload


@pytest.mark.integration
@pytest.mark.asyncio
async def test_interrupted_turn_is_not_replayed_automatically(stf_db):  # noqa: F811
    _, factory = stf_db
    creator_id, conversation_id = await _conversation(factory)
    store = TurnStore(factory)
    request_id = str(uuid.uuid4())

    first = await store.claim(creator_id, conversation_id, request_id, "Faça algo")
    await store.finish(first, None, "interrupted")

    with pytest.raises(TurnConflict, match="use a new request_id"):
        await store.claim(creator_id, conversation_id, request_id, "Faça algo")
