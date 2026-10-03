from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.knowledge.contracts import Candidate, Scope
from app.knowledge.service import KnowledgeService
from app.models.entities import Conversation, Creator, Message
from app.models.knowledge import KnowledgeItem, KnowledgeRevision


async def backfill(factory=AsyncSessionLocal, dry_run: bool = True) -> dict[str, int]:
    scanned = written = offset = 0
    while True:
        async with factory() as session:
            rows = list((await session.execute(select(Message, Conversation.creator_id).join(Conversation, Conversation.id == Message.conversation_id).join(Creator, Creator.id == Conversation.creator_id).where(Message.role == 'creator', Creator.is_active.is_(True)).order_by(Message.id).limit(100).offset(offset))).all())
            if not rows:
                break
            for message, creator_id in rows:
                scanned += 1
                # A canonical source already ingested or revoked must not be cloned or resurrected.
                known = await session.scalar(select(KnowledgeRevision).where(
                    KnowledgeRevision.creator_id==creator_id, KnowledgeRevision.source_type=='message',
                    KnowledgeRevision.source_id==message.id).limit(1))
                if known:
                    if not dry_run:
                        item = await session.get(KnowledgeItem, known.item_id)
                        message.metadata_json = {**(message.metadata_json or {}),
                            'knowledge_revision_id':known.id,
                            'knowledge_project_id':item.project_id if item else None}
                    continue
                if not dry_run and message.content.strip() and len(message.content.encode()) <= 262144:
                    result = await KnowledgeService(session).write(Scope(creator_id=creator_id), Candidate(title='Conversa: ' + message.role, content=message.content, kind='derived_note' if message.role == 'deus' else 'document', source_type='message', source_id=message.id), 'message:' + message.id)
                    item = await session.get(KnowledgeItem, result.item_id)
                    message.metadata_json = {**(message.metadata_json or {}),
                        'knowledge_revision_id':result.revision_id,
                        'knowledge_project_id':item.project_id if item else None}
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
