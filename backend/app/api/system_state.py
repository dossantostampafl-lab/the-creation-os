from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
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


async def _stream_chronicle(request: Request, after: int) -> AsyncIterator[str]:
    cursor = after
    while not await request.is_disconnected():
        async with AsyncSessionLocal() as session:
            events = list((await session.scalars(
                select(Chronicle)
                .where(Chronicle.position > cursor)
                .order_by(Chronicle.position)
                .limit(100)
            )).all())

        if events:
            if cursor > 0 and events[0].position != cursor + 1:
                payload = {"status": "RESYNCING", "expected": cursor + 1, "received": events[0].position}
                yield f"event: resync_required\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"
                return
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
