from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.living_core import actor
from app.core.domain import Actor
from app.db.session import AsyncSessionLocal, get_session
from app.models.entities import Chronicle
from app.projections.system import system_snapshot

router = APIRouter(tags=["system-state"])


@router.get("/system/state")
async def get_system_state(
    _: Actor = Depends(actor),
    session: AsyncSession = Depends(get_session),
):
    return await system_snapshot(session)


@router.get("/system/events")
async def system_events(
    request: Request,
    after: int = Query(0, ge=0),
    _: Actor = Depends(actor),
):
    return StreamingResponse(
        _stream_chronicle(request, after),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def cursor_resync_reason(*, after: int, head: int, first_position: int | None) -> dict | None:
    if after > head:
        return {
            "status": "RESYNCING",
            "reason": "cursor_ahead",
            "expected_max": head,
            "received": after,
        }
    if after > 0 and first_position is not None and first_position != after + 1:
        return {
            "status": "RESYNCING",
            "reason": "gap",
            "expected": after + 1,
            "received": first_position,
        }
    return None


async def _stream_chronicle(request: Request, after: int) -> AsyncIterator[str]:
    cursor = after
    while not await request.is_disconnected():
        async with AsyncSessionLocal() as session:
            head = int(await session.scalar(select(func.max(Chronicle.position))) or 0)
            events = list((await session.scalars(
                select(Chronicle)
                .where(Chronicle.position > cursor)
                .order_by(Chronicle.position)
                .limit(100)
            )).all())

        first_position = events[0].position if events else None
        resync = cursor_resync_reason(after=cursor, head=head, first_position=first_position)
        if resync is not None:
            yield f"event: resync_required\ndata: {json.dumps(resync, separators=(',', ':'))}\n\n"
            return

        if events:
            for event in events:
                payload = {
                    "event_id": event.event_id,
                    "position": event.position,
                    "correlation_id": event.correlation_id,
                    "causation_id": event.causation_id,
                    "actor_role": event.actor_role,
                    "event_type": event.event_type,
                    "aggregate_type": event.aggregate_type,
                    "aggregate_id": event.aggregate_id,
                    "payload": event.payload_json,
                    "created_at": event.created_at.isoformat(),
                }
                encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
                yield f"id: {event.position}\nevent: chronicle\ndata: {encoded}\n\n"
                cursor = event.position
            continue

        yield ": keepalive\n\n"
        await asyncio.sleep(1.0)
