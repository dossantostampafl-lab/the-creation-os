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
from app.models.projection import ProjectionCheckpoint
from app.projections.checkpoints import projection_lag
from app.projections.system import (
    AGENT_PROJECTION,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    MEMORY_PROJECTION,
    MISSION_PROJECTION,
    SYSTEM_PROJECTION,
    TASK_PROJECTION,
    system_snapshot,
)

router = APIRouter(tags=["system-state"])
EXPECTED_PROJECTIONS = (
    SYSTEM_PROJECTION,
    MISSION_PROJECTION,
    TASK_PROJECTION,
    AGENT_PROJECTION,
    MEMORY_PROJECTION,
)


@router.get("/system/state")
async def get_system_state(
    _: Actor = Depends(actor),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1, le=100_000),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    offset = (page - 1) * page_size
    return await system_snapshot(session, persist=False, limit=page_size, offset=offset)


@router.get("/system/projections")
async def get_projection_status(
    _: Actor = Depends(actor),
    session: AsyncSession = Depends(get_session),
):
    head = int(await session.scalar(select(func.max(Chronicle.position))) or 0)
    rows = list((await session.scalars(select(ProjectionCheckpoint))).all())
    by_name = {row.projection_name: row for row in rows}
    projections = []
    for name in EXPECTED_PROJECTIONS:
        checkpoint = by_name.get(name)
        if checkpoint is None:
            projections.append({"name": name, "position": None, "lag": head, "status": "MISSING"})
            continue
        try:
            lag = projection_lag(head=head, checkpoint=checkpoint.position)
            status = "CURRENT" if lag == 0 else "LAGGING"
        except ValueError:
            lag = None
            status = "INVALID"
        projections.append(
            {
                "name": name,
                "position": checkpoint.position,
                "lag": lag,
                "status": status,
                "updated_at": checkpoint.updated_at.isoformat(),
            }
        )
    return {"chronicle_head": head, "projections": projections}


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
