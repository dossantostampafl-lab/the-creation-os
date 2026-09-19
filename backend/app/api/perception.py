from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.core.domain import Actor
from app.db.session import get_session
from app.models.perception import CreatorNotification, PerceptionRun, PerceptionSource
from app.repositories.perception import PerceptionRepository
from app.schemas.auth import TokenPayload
from app.schemas.perception import (
    NotificationResponse,
    PerceptionRunResponse,
    PerceptionRunResult,
    PerceptionSourceResponse,
    SchedulerRunResponse,
)
from app.services.perception import CollectionResult, PerceptionService

router = APIRouter(tags=["perception"], dependencies=[Depends(get_sovereign_creator)])


def correlation_id(x_correlation_id: str | None = Header(None)) -> str:
    return str(uuid.UUID(x_correlation_id)) if x_correlation_id else str(uuid.uuid4())


def actor(token: TokenPayload = Depends(get_sovereign_creator)) -> Actor:
    return Actor(id=token.sub, role="creator")


def service(session: AsyncSession = Depends(get_session)) -> PerceptionService:
    return PerceptionService(PerceptionRepository(session))


def source_state(item: PerceptionSource) -> str:
    now = datetime.now(timezone.utc)
    if not item.enabled:
        return "disabled"
    next_run = item.next_run_at if item.next_run_at is None or item.next_run_at.tzinfo else item.next_run_at.replace(tzinfo=timezone.utc)
    if item.failure_count >= item.max_consecutive_failures and next_run and next_run > now:
        return "suspended"
    return "enabled"


def source_response(item: PerceptionSource) -> PerceptionSourceResponse:
    return PerceptionSourceResponse(
        id=item.id,
        name=item.name,
        universe=item.universe,
        provider=item.provider,
        capability_name=item.capability_name,
        connector_name=item.connector_name,
        enabled=item.enabled,
        state=source_state(item),
        schedule_interval_seconds=item.schedule_interval_seconds,
        minimum_interval_seconds=item.minimum_interval_seconds,
        last_started_at=item.last_started_at,
        last_succeeded_at=item.last_succeeded_at,
        last_failed_at=item.last_failed_at,
        failure_count=item.failure_count,
        max_consecutive_failures=item.max_consecutive_failures,
        next_run_at=item.next_run_at,
        last_cursor=item.last_cursor,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def run_response(item: PerceptionRun) -> PerceptionRunResponse:
    return PerceptionRunResponse(
        id=item.id,
        source_id=item.source_id,
        status=item.status,
        started_at=item.started_at,
        completed_at=item.completed_at,
        duration_ms=item.duration_ms,
        observations_count=item.observations_count,
        opportunities_count=item.opportunities_count,
        attempts_count=item.attempts_count,
        error_code=item.error_code,
        error_message=item.error_message,
        metadata_json=item.metadata_json,
        created_at=item.created_at,
    )


def notification_response(item: CreatorNotification) -> NotificationResponse:
    return NotificationResponse(
        id=item.id,
        recipient_actor_id=item.recipient_actor_id,
        type=item.type,
        title=item.title,
        message=item.message,
        opportunity_id=item.opportunity_id,
        priority_score=item.priority_score,
        status=item.status,
        created_at=item.created_at,
        read_at=item.read_at,
        acknowledged_at=item.acknowledged_at,
    )


def run_result_response(result: CollectionResult) -> PerceptionRunResult:
    return PerceptionRunResult(
        source=source_response(result.source),
        run=run_response(result.run),
        observations_count=result.observations_count,
        opportunities_count=result.opportunities_count,
        notifications_count=result.notifications_count,
    )


@router.get("/perception/sources", response_model=list[PerceptionSourceResponse])
async def list_sources(
    universe: str | None = None,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    s: PerceptionService = Depends(service),
):
    return [source_response(item) for item in await s.list_sources(a, universe, cid)]


@router.post("/perception/sources/{source_id}/enable", response_model=PerceptionSourceResponse)
async def enable_source(source_id: uuid.UUID, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: PerceptionService = Depends(service)):
    return source_response(await s.enable_source(a, str(source_id), cid))


@router.post("/perception/sources/{source_id}/disable", response_model=PerceptionSourceResponse)
async def disable_source(source_id: uuid.UUID, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: PerceptionService = Depends(service)):
    return source_response(await s.disable_source(a, str(source_id), cid))


@router.post("/perception/sources/{source_id}/run", response_model=PerceptionRunResult)
async def run_source(source_id: uuid.UUID, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: PerceptionService = Depends(service)):
    return run_result_response(await s.run_source(a, str(source_id), cid, force=True))


@router.get("/perception/sources/{source_id}/runs", response_model=list[PerceptionRunResponse])
async def source_runs(
    source_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    a: Actor = Depends(actor),
    s: PerceptionService = Depends(service),
):
    return [run_response(item) for item in await s.source_runs(a, str(source_id), limit)]


@router.post("/perception/scheduler/run", response_model=SchedulerRunResponse)
async def run_scheduler(a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: PerceptionService = Depends(service)):
    return SchedulerRunResponse(results=[run_result_response(item) for item in await s.run_due_sources(a, cid)])


@router.get("/notifications", response_model=list[NotificationResponse])
async def list_notifications(
    status: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    s: PerceptionService = Depends(service),
):
    return [notification_response(item) for item in await s.list_notifications(a, status, limit, offset, cid)]


@router.post("/notifications/{notification_id}/read", response_model=NotificationResponse)
async def read_notification(notification_id: uuid.UUID, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: PerceptionService = Depends(service)):
    return notification_response(await s.mark_notification_read(a, str(notification_id), cid))


@router.post("/notifications/{notification_id}/acknowledge", response_model=NotificationResponse)
async def acknowledge_notification(notification_id: uuid.UUID, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: PerceptionService = Depends(service)):
    return notification_response(await s.acknowledge_notification(a, str(notification_id), cid))
