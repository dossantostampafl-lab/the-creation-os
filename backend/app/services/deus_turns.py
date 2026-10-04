from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.knowledge.service import digest
from app.models.entities import Conversation, uuid_string
from app.models.knowledge import ConversationTurn


class TurnConflict(ValueError):
    pass

class TurnStore:
    def __init__(self, factory: async_sessionmaker[AsyncSession]):
        self.factory = factory

    async def claim(self, creator_id: str, conversation_id: str, request_id: str, content: str) -> ConversationTurn:
        now = datetime.now(timezone.utc)
        owner = uuid_string()
        async with self.factory() as session, session.begin():
            conversation = await session.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.creator_id == creator_id, Conversation.status == 'active'))
            if not conversation:
                raise LookupError('Conversation unavailable')
            await session.execute(insert(ConversationTurn).values(id=uuid_string(), conversation_id=conversation_id, request_id=request_id, content_hash=digest(content), owner=owner, state='pending', lease_until=now+timedelta(seconds=120)).on_conflict_do_nothing(index_elements=['conversation_id','request_id']))
            row = await session.scalar(select(ConversationTurn).where(ConversationTurn.conversation_id == conversation_id, ConversationTurn.request_id == request_id).with_for_update())
            assert row
            if row.content_hash != digest(content):
                raise TurnConflict('request_id has different content')
            if row.owner != owner:
                if row.state == 'completed':
                    return row
                # A clean provider failure is known to have produced no committed domain
                # effects, so the same idempotency key may safely acquire a fresh lease.
                # Interrupted/expired work remains fenced because its outcome is uncertain.
                if row.state == 'failed':
                    row.owner = owner
                    row.state = 'pending'
                    row.lease_until = now + timedelta(seconds=120)
                    row.response = None
                    await session.flush()
                    return row
                if row.state == 'pending' and row.lease_until <= now:
                    row.state = 'failed'
                    # Expiration is not permission to repeat reasoning or effects.
                    await session.commit()
                raise TurnConflict('turn_in_progress_or_interrupted; use a new request_id to repeat')
            return row

    async def renew(self, turn: ConversationTurn) -> bool:
        async with self.factory() as session, session.begin():
            changed = await session.execute(update(ConversationTurn).where(ConversationTurn.id == turn.id, ConversationTurn.owner == turn.owner, ConversationTurn.state == 'pending', ConversationTurn.lease_until > datetime.now(timezone.utc)).values(lease_until=datetime.now(timezone.utc)+timedelta(seconds=120)))
            return bool(cast(CursorResult[Any], changed).rowcount)

    async def finish_in_session(self, session: AsyncSession, turn: ConversationTurn, response: dict | None, state: str) -> None:
        """Fence domain effects and terminal state in the SAME transaction."""
        if state not in {'completed', 'interrupted', 'failed'}:
            raise ValueError('invalid terminal state')
        changed = await session.execute(update(ConversationTurn).where(
            ConversationTurn.id == turn.id, ConversationTurn.owner == turn.owner,
            ConversationTurn.state == 'pending',
            ConversationTurn.lease_until > datetime.now(timezone.utc)
        ).values(state=state, response=response))
        if not cast(CursorResult[Any], changed).rowcount:
            raise TurnConflict('generation ownership expired')

    async def finish(self, turn: ConversationTurn, response: dict | None, state: str) -> None:
        async with self.factory() as session, session.begin():
            await self.finish_in_session(session, turn, response, state)

    @asynccontextmanager
    async def renewing(self, turn: ConversationTurn):
        generation = asyncio.current_task()
        lost = False
        async def heartbeat():
            nonlocal lost
            while True:
                await asyncio.sleep(20)
                try:
                    renewed = await self.renew(turn)
                except Exception:
                    renewed = False
                if not renewed:
                    lost = True
                    if generation:
                        generation.cancel()
                    return
        task = asyncio.create_task(heartbeat())
        try:
            yield
        except asyncio.CancelledError:
            if lost:
                raise TurnConflict('generation ownership expired') from None
            raise
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
