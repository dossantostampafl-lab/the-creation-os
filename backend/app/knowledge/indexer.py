from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.knowledge import KnowledgeOutbox, KnowledgeReceipt
from app.observability.telemetry import traced


@traced("workers.knowledge")
async def process_batch(factory: async_sessionmaker[AsyncSession], consumer: str = "knowledge", limit: int = 100) -> int:
    async with factory() as session, session.begin():
        # PostgreSQL sequences do not order commits. Discover unreceipted events, not a watermark.
        done = exists(select(KnowledgeReceipt.sequence).where(KnowledgeReceipt.sequence == KnowledgeOutbox.sequence, KnowledgeReceipt.consumer == consumer))
        events = list(await session.scalars(select(KnowledgeOutbox).where(~done).order_by(KnowledgeOutbox.sequence).limit(limit).with_for_update(skip_locked=True)))
        for event in events:
            # FTS is a generated indexed column, transactionally current even before this consumer runs.
            session.add(KnowledgeReceipt(consumer=consumer, sequence=event.sequence))
        return len(events)
