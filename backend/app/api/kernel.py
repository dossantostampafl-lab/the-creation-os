from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.living_core import actor, correlation_id, mission_response, service
from app.core.domain import Actor, MissionStatus
from app.db.session import get_session
from app.models.entities import Task
from app.schemas.mission import MissionResponse, TaskResponse
from app.services.domain import LivingCoreService

router = APIRouter(tags=["creation-kernel"])


@router.post("/missions/{entity_id}/distribute", response_model=MissionResponse)
async def distribute_mission(
    entity_id: uuid.UUID,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    s: LivingCoreService = Depends(service),
):
    return mission_response(await s.transition_mission(a, str(entity_id), MissionStatus.DISTRIBUTED, cid))


@router.post("/missions/{entity_id}/execute", response_model=MissionResponse)
async def execute_mission(
    entity_id: uuid.UUID,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    s: LivingCoreService = Depends(service),
):
    return mission_response(await s.transition_mission(a, str(entity_id), MissionStatus.EXECUTING, cid))


@router.post("/missions/{entity_id}/manifest", response_model=MissionResponse)
async def manifest_mission(
    entity_id: uuid.UUID,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    s: LivingCoreService = Depends(service),
):
    return mission_response(await s.transition_mission(a, str(entity_id), MissionStatus.MANIFESTED, cid))


@router.post("/missions/{entity_id}/fail", response_model=MissionResponse)
async def fail_mission(
    entity_id: uuid.UUID,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    s: LivingCoreService = Depends(service),
):
    return mission_response(await s.transition_mission(a, str(entity_id), MissionStatus.FAILED, cid))


@router.get("/missions/{entity_id}/tasks", response_model=list[TaskResponse])
async def mission_tasks(
    entity_id: uuid.UUID,
    a: Actor = Depends(actor),
    s: LivingCoreService = Depends(service),
    session: AsyncSession = Depends(get_session),
):
    await s.mission(a, str(entity_id))
    tasks = list((await session.scalars(
        select(Task).where(Task.mission_id == str(entity_id)).order_by(Task.created_at, Task.id)
    )).all())
    return [TaskResponse(**{name: getattr(task, name) for name in TaskResponse.model_fields}) for task in tasks]
