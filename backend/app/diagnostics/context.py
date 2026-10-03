from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeItem, KnowledgeRevision


def _safe_evidence(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, object] = {}
    for key, item in list(value.items())[:8]:
        safe_key = str(key)[:64]
        if isinstance(item, (bool, int, float)) or item is None:
            result[safe_key] = item
        else:
            result[safe_key] = str(item)[:128]
    return result


async def current_diagnostics(
    session: AsyncSession,
    creator_id: str,
) -> list[dict]:
    rows = await session.scalars(
        select(KnowledgeRevision)
        .join(
            KnowledgeItem,
            KnowledgeItem.current_revision_id == KnowledgeRevision.id,
        )
        .where(
            KnowledgeItem.creator_id == creator_id,
            KnowledgeItem.active.is_(True),
            KnowledgeRevision.kind == "diagnostic",
            KnowledgeRevision.valid_until > datetime.now(timezone.utc),
        )
        .order_by(KnowledgeRevision.created_at.desc())
        .limit(100)
    )
    current: dict[str, dict] = {}
    for row in rows:
        try:
            data = json.loads(row.content)
            resource = data.get("resource")
            if data.get("type") != "observation" or not resource or resource in current:
                continue
            current[resource] = {
                key: str(data.get(key, ""))[:64]
                for key in ["resource", "status", "observed_at", "valid_until"]
            }
            latency_ms = data.get("latency_ms")
            if isinstance(latency_ms, (int, float)) and latency_ms >= 0:
                current[resource]["latency_ms"] = round(latency_ms)
            evidence = _safe_evidence(data.get("safe_evidence"))
            if evidence:
                current[resource]["safe_evidence"] = evidence
            current[resource].update(
                {"revision_id": row.id, "item_id": row.item_id}
            )
        except (ValueError, TypeError, AttributeError):
            continue
    return list(current.values())
