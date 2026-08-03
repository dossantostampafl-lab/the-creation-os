from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.dispatch import DispatchItem
from app.models.entities import Agent, Chronicle, Inception, Mission, Task, Universe
from app.observability.metrics import request_metrics
from app.repositories.domain import DomainRepository


async def _scalar_count(session: AsyncSession, stmt) -> int:
    return int(await session.scalar(stmt) or 0)


async def build_pulse_snapshot(session: AsyncSession) -> dict[str, Any]:
    """The single source of truth for system-health data: GET /api/v1/pulse and
    DEUS's SYSTEM_QUERY "pulse"/"general" topics both call this, instead of
    each keeping their own copy of these queries."""
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
    active_universes = await _scalar_count(session, select(func.count()).select_from(Universe).where(Universe.active.is_(True)))
    active_agents = await _scalar_count(session, select(func.count()).select_from(Agent).where(Agent.enabled.is_(True)))
    running_missions = await _scalar_count(
        session,
        select(func.count()).select_from(Mission).where(func.lower(Mission.status).in_(["planned", "authorized", "running"])),
    )
    pending_inceptions = await _scalar_count(
        session,
        select(func.count()).select_from(Inception).where(func.lower(Inception.status).in_(["proposed", "submitted", "pending"])),
    )
    pending_tasks = await _scalar_count(
        session,
        select(func.count()).select_from(Task).where(func.lower(Task.status).in_(["pending", "created", "queued"])),
    )
    failed_tasks = await _scalar_count(session, select(func.count()).select_from(Task).where(func.lower(Task.status) == "failed"))
    error_count = await _scalar_count(session, select(func.count()).select_from(Chronicle).where(Chronicle.event_type.ilike("%failed%")))

    # Lote: métricas de observabilidade faltantes. Real data, same pattern
    # as the rest of Pulse — new fields, existing ones untouched.
    approved_inceptions = await _scalar_count(
        session, select(func.count()).select_from(Inception).where(func.lower(Inception.status) == "approved")
    )
    total_missions_created = await _scalar_count(session, select(func.count()).select_from(Mission))
    # Deliberately sourced from DispatchItem, not Task.state/Task.status:
    # confirmed by grep across app/services and app/core that nothing in
    # this codebase ever writes Task.state to COMPLETED/FAILED, nor
    # Task.status to anything but its DB default — the existing
    # pending_tasks/failed_tasks fields above query a column real dispatch/
    # execution outcomes never update. DispatchItem.state *is* the field
    # DispatchService/AgentExecutionService actually maintain, so it's the
    # real signal for "did this unit of work actually finish". Named
    # distinctly (not "completed_tasks") specifically so it's not mistaken
    # for a Task-table equivalent of pending_tasks/failed_tasks above — see
    # ARCHITECTURE.md for the full finding; the existing fields are left
    # exactly as they are (not this lote's scope to fix).
    dispatch_items_acknowledged = await _scalar_count(
        session, select(func.count()).select_from(DispatchItem).where(DispatchItem.state == "acknowledged")
    )
    dispatch_queue_depth = await _scalar_count(
        session, select(func.count()).select_from(DispatchItem).where(DispatchItem.state.in_(["queued", "retry_scheduled"]))
    )
    http_metrics = request_metrics.snapshot()

    return {
        "status": "live" if database["status"] == "ok" and integrity.valid else "degraded",
        "database": database,
        "redis": redis_status,
        "redis_streams": redis_streams,
        "chronicles_chain": {"valid": integrity.valid, "reason": integrity.reason, "first_invalid_event_id": integrity.first_invalid_event_id},
        "active_universes": active_universes,
        "active_agents": active_agents,
        "running_missions": running_missions,
        "pending_inceptions": pending_inceptions,
        "pending_tasks": pending_tasks,
        "failed_tasks": failed_tasks,
        "error_count": error_count,
        "approved_inceptions": approved_inceptions,
        "total_missions_created": total_missions_created,
        "dispatch_items_acknowledged": dispatch_items_acknowledged,
        "dispatch_queue_depth": dispatch_queue_depth,
        "http_requests_total": http_metrics["http_requests_total"],
        "http_errors_total": http_metrics["http_errors_total"],
        "http_average_latency_ms": http_metrics["http_average_latency_ms"],
        "timestamp": datetime.now(timezone.utc),
    }
