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


async def system_snapshot(session: AsyncSession, *, persist: bool = True) -> dict[str, Any]:
    missions = list((await session.scalars(select(Mission).order_by(Mission.created_at, Mission.id))).all())
    tasks = list((await session.scalars(select(Task).order_by(Task.created_at, Task.id))).all())
    universes = list((await session.scalars(select(Universe).order_by(Universe.code))).all())
    agents = list((await session.scalars(select(Agent).order_by(Agent.code))).all())
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
            "missions": len(missions),
            "running_missions": sum(mission.status in {"distributed", "executing"} for mission in missions),
            "tasks": len(tasks),
            "ready_tasks": sum(task.status == "READY" for task in tasks),
            "running_tasks": sum(task.status == "RUNNING" for task in tasks),
            "failed_tasks": sum(task.status in {"FAILED", "BLOCKED"} for task in tasks),
            "active_universes": sum(universe.active for universe in universes),
            "active_agents": sum(agent.active for agent in agents),
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
