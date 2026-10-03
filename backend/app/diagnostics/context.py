from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeItem, KnowledgeRevision


async def current_diagnostics(session: AsyncSession, creator_id: str) -> list[dict]:
    rows = await session.scalars(select(KnowledgeRevision).join(KnowledgeItem,
        KnowledgeItem.current_revision_id==KnowledgeRevision.id).where(
            KnowledgeItem.creator_id==creator_id, KnowledgeItem.active.is_(True),
            KnowledgeRevision.kind=='diagnostic',
            KnowledgeRevision.valid_until>datetime.now(timezone.utc)).order_by(
                KnowledgeRevision.created_at.desc()).limit(100))
    current: dict[str, dict] = {}
    for row in rows:
        try:
            data = json.loads(row.content)
            if data.get('type')=='observation' and data.get('resource') not in current:
                current[data['resource']] = {key:str(data.get(key,''))[:64] for key in ['resource','status','observed_at','valid_until']}
                current[data['resource']].update({'revision_id':row.id,'item_id':row.item_id})
        except (ValueError, TypeError, AttributeError):
            continue
    return list(current.values())
