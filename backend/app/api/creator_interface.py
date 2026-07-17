from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.config import settings
from app.db.session import get_session
from app.models.entities import Agent, Chronicle, Inception, Mission, Task, Universe
from app.repositories.domain import DomainRepository
from app.schemas.chronicle import ChronicleResponse
from app.schemas.pulse import PulseResponse
from app.schemas.tree_core import UniverseResponse

router = APIRouter(tags=["creator-interface"], dependencies=[Depends(get_sovereign_creator)])


def chronicle_response(item: Chronicle) -> ChronicleResponse:
    return ChronicleResponse(
        id=item.id,
        event_id=item.event_id,
        position=item.position,
        correlation_id=item.correlation_id,
        causation_id=item.causation_id,
        actor_type=item.actor_type,
        actor_role=item.actor_role,
        actor_id=item.actor_id,
        event_type=item.event_type,
        aggregate_type=item.aggregate_type,
        aggregate_id=item.aggregate_id,
        payload_json=item.payload_json,
        payload_hash=item.payload_hash,
        previous_hash=item.previous_hash,
        created_at=item.created_at,
    )


def universe_response(item: Universe) -> UniverseResponse:
    return UniverseResponse(
        id=item.id,
        code=item.code,
        name=item.name,
        active=item.active,
        created_at=item.created_at,
    )


async def scalar_count(session: AsyncSession, stmt) -> int:
    return int(await session.scalar(stmt) or 0)


@router.get("/chronicles", response_model=list[ChronicleResponse])
async def list_chronicles(
    limit: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    result = await session.scalars(select(Chronicle).order_by(Chronicle.position.desc()).limit(limit))
    return [chronicle_response(item) for item in result.all()]


@router.get("/universes", response_model=list[UniverseResponse])
async def list_universes(session: AsyncSession = Depends(get_session)):
    result = await session.scalars(select(Universe).order_by(Universe.name, Universe.code))
    return [universe_response(item) for item in result.all()]


@router.get("/pulse", response_model=PulseResponse)
async def pulse(session: AsyncSession = Depends(get_session)):
    database = {"status": "unknown"}
    redis_status = {"status": "unknown"}
    redis_streams = {"status": "not_inspected"}

    try:
        await session.execute(text("SELECT 1"))
        database = {"status": "ok"}
    except Exception as exc:
        database = {"status": "error", "detail": exc.__class__.__name__}

    redis = Redis.from_url(settings.redis_url)
    try:
        async with asyncio.timeout(2):
            redis_status = {"status": "ok" if await redis.ping() else "error"}
    except Exception as exc:
        redis_status = {"status": "error", "detail": exc.__class__.__name__}
    finally:
        await redis.aclose()

    integrity = await DomainRepository(session).verify_chronicle()
    active_universes = await scalar_count(session, select(func.count()).select_from(Universe).where(Universe.active.is_(True)))
    active_agents = await scalar_count(session, select(func.count()).select_from(Agent).where(Agent.enabled.is_(True)))
    running_missions = await scalar_count(
        session,
        select(func.count()).select_from(Mission).where(func.lower(Mission.status).in_(["planned", "authorized", "running"])),
    )
    pending_inceptions = await scalar_count(
        session,
        select(func.count()).select_from(Inception).where(func.lower(Inception.status).in_(["proposed", "submitted", "pending"])),
    )
    pending_tasks = await scalar_count(
        session,
        select(func.count()).select_from(Task).where(func.lower(Task.status).in_(["pending", "created", "queued"])),
    )
    failed_tasks = await scalar_count(session, select(func.count()).select_from(Task).where(func.lower(Task.status) == "failed"))
    error_count = await scalar_count(session, select(func.count()).select_from(Chronicle).where(Chronicle.event_type.ilike("%failed%")))

    return PulseResponse(
        status="live" if database["status"] == "ok" and integrity.valid else "degraded",
        database=database,
        redis=redis_status,
        redis_streams=redis_streams,
        chronicles_chain={"valid": integrity.valid, "reason": integrity.reason, "first_invalid_event_id": integrity.first_invalid_event_id},
        active_universes=active_universes,
        active_agents=active_agents,
        running_missions=running_missions,
        pending_inceptions=pending_inceptions,
        pending_tasks=pending_tasks,
        failed_tasks=failed_tasks,
        error_count=error_count,
        timestamp=datetime.now(timezone.utc),
    )
