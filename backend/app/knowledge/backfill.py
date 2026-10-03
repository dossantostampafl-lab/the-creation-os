from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.knowledge.contracts import Candidate, Scope
from app.knowledge.service import KnowledgeService, digest
from app.models.entities import Conversation, Creator, Message


async def backfill(factory=AsyncSessionLocal, dry_run: bool = True) -> dict[str, int]:
    scanned = written = offset = 0
    while True:
        async with factory() as session:
            rows = list((await session.execute(select(Message, Conversation.creator_id).join(Conversation, Conversation.id == Message.conversation_id).join(Creator, Creator.id == Conversation.creator_id).where(Message.role == 'creator', Creator.is_active.is_(True)).order_by(Message.id).limit(100).offset(offset))).all())
            if not rows:
                break
            for message, creator_id in rows:
                scanned += 1
                if not dry_run and message.content.strip() and len(message.content.encode()) <= 262144:
                    await KnowledgeService(session).write(Scope(creator_id=creator_id), Candidate(title='Conversa: ' + message.role, content=message.content, kind='derived_note' if message.role == 'deus' else 'document', source_type='message', source_id=message.id), 'backfill:' + message.id + ':' + digest(message.content))
                    written += 1
            if not dry_run:
                await session.commit()
            offset += len(rows)
    return {'scanned': scanned, 'written': written}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(asyncio.run(backfill(dry_run=not args.apply)))
