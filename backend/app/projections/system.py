from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import (
    Agent,
    Chronicle,
    ConsciousMemory,
    ConversationMemory,
    Mission,
    MissionMemory,
    PulseMetric,
    Task,
    Universe,
    UniverseMemory,
)
from app.projections.checkpoints import save_checkpoint

SYSTEM_PROJECTION = "system"
MISSION_PROJECTION = "missions"
TASK_PROJECTION = "tasks"
AGENT_PROJECTION = "agents"
MEMORY_PROJECTION = "memory"

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


def page_window(*, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0) -> tuple[int, int]:
    if limit < 1 or limit > MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    if offset < 0:
        raise ValueError("offset must be non-negative")
    return limit, offset


async def system_snapshot(
    session: AsyncSession,
    *,
    persist: bool = True,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
) -> dict[str, Any]:
    limit, offset = page_window(limit=limit, offset=offset)

    mission_total = int(await session.scalar(select(func.count()).select_from(Mission)) or 0)
    task_total = int(await session.scalar(select(func.count()).select_from(Task)) or 0)
    universe_total = int(await session.scalar(select(func.count()).select_from(Universe)) or 0)
    agent_total = int(await session.scalar(select(func.count()).select_from(Agent)) or 0)
    running_missions_total = int(await session.scalar(
        select(func.count()).select_from(Mission).where(Mission.status.in_({"distributed", "executing"}))
    ) or 0)
    ready_tasks_total = int(await session.scalar(
        select(func.count()).select_from(Task).where(Task.status == "READY")
    ) or 0)
    running_tasks_total = int(await session.scalar(
        select(func.count()).select_from(Task).where(Task.status == "RUNNING")
    ) or 0)
    failed_tasks_total = int(await session.scalar(
        select(func.count()).select_from(Task).where(Task.status.in_({"FAILED", "BLOCKED"}))
    ) or 0)
    active_universes_total = int(await session.scalar(
        select(func.count()).select_from(Universe).where(Universe.active.is_(True))
    ) or 0)
    active_agents_total = int(await session.scalar(
        select(func.count()).select_from(Agent).where(Agent.active.is_(True))
    ) or 0)

    missions = list((await session.scalars(
        select(Mission).order_by(Mission.created_at, Mission.id).offset(offset).limit(limit)
    )).all())
    tasks = list((await session.scalars(
        select(Task).order_by(Task.created_at, Task.id).offset(offset).limit(limit)
    )).all())
    universes = list((await session.scalars(
        select(Universe).order_by(Universe.code).offset(offset).limit(limit)
    )).all())
    agents = list((await session.scalars(
        select(Agent).order_by(Agent.code).offset(offset).limit(limit)
    )).all())
    position = int(await session.scalar(select(func.max(Chronicle.position))) or 0)

    conversation_memory = int(await session.scalar(select(func.count()).select_from(ConversationMemory)) or 0)
    mission_memory = int(await session.scalar(select(func.count()).select_from(MissionMemory)) or 0)
    universe_memory = int(await session.scalar(select(func.count()).select_from(UniverseMemory)) or 0)
    conscious_memory = int(await session.scalar(select(func.count()).select_from(ConsciousMemory)) or 0)

    pulse_rows = list((await session.scalars(
        select(PulseMetric).order_by(PulseMetric.created_at.desc(), PulseMetric.id.desc()).limit(200)
    )).all())
    pulse: dict[str, Any] = {}
    for metric in pulse_rows:
        if metric.metric_name not in pulse:
            pulse[metric.metric_name] = {
                "value": metric.metric_value_json,
                "observed_at": metric.created_at.isoformat(),
            }

    mission_view = [
        {
            "id": mission.id,
            "title": mission.title,
            "objective": mission.objective,
            "status": mission.status,
            "started_at": mission.started_at.isoformat() if mission.started_at else None,
            "completed_at": mission.completed_at.isoformat() if mission.completed_at else None,
        }
        for mission in missions
    ]
    task_view = [
        {
            "id": task.id,
            "mission_id": task.mission_id,
            "step_id": task.step_id,
            "universe_id": task.universe_id,
            "agent_id": task.agent_id,
            "status": task.status,
            "attempt_count": task.attempt_count,
            "max_attempts": task.max_attempts,
        }
        for task in tasks
    ]
    universe_view = [
        {"id": universe.id, "code": universe.code, "name": universe.name, "active": universe.active}
        for universe in universes
    ]
    agent_view = [
        {
            "id": agent.id,
            "code": agent.code,
            "name": agent.name,
            "universe_id": agent.universe_id,
            "active": agent.active,
        }
        for agent in agents
    ]
    memory_view = {
        "conversation": conversation_memory,
        "mission": mission_memory,
        "universe": universe_memory,
        "conscious": conscious_memory,
        "total": conversation_memory + mission_memory + universe_memory + conscious_memory,
    }

    snapshot: dict[str, Any] = {
        "projection": SYSTEM_PROJECTION,
        "position": position,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "missions": mission_view,
        "tasks": task_view,
        "universes": universe_view,
        "agents": agent_view,
        "memory": memory_view,
        "pulse": pulse,
        "counts": {
            "missions": mission_total,
            "running_missions": running_missions_total,
            "tasks": task_total,
            "ready_tasks": ready_tasks_total,
            "running_tasks": running_tasks_total,
            "failed_tasks": failed_tasks_total,
            "active_universes": active_universes_total,
            "active_agents": active_agents_total,
        },
        "pagination": {
            "limit": limit,
            "offset": offset,
            "has_next": any(total > offset + limit for total in (mission_total, task_total, universe_total, agent_total)),
            "totals": {
                "missions": mission_total,
                "tasks": task_total,
                "universes": universe_total,
                "agents": agent_total,
            },
        },
    }
    if persist:
        checkpoints = {
            SYSTEM_PROJECTION: snapshot,
            MISSION_PROJECTION: {"position": position, "missions": mission_view},
            TASK_PROJECTION: {"position": position, "tasks": task_view},
            AGENT_PROJECTION: {"position": position, "agents": agent_view, "universes": universe_view},
            MEMORY_PROJECTION: {"position": position, "memory": memory_view},
        }
        for projection_name, state in checkpoints.items():
            await save_checkpoint(
                session,
                projection_name=projection_name,
                position=position,
                state=state,
            )
        await session.commit()
    return snapshot
