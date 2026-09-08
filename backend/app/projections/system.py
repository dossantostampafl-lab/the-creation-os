from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Agent, Chronicle, Mission, Task, Universe


async def system_snapshot(session: AsyncSession) -> dict[str, Any]:
    missions = list((await session.scalars(select(Mission).order_by(Mission.created_at, Mission.id))).all())
    tasks = list((await session.scalars(select(Task).order_by(Task.created_at, Task.id))).all())
    universes = list((await session.scalars(select(Universe).order_by(Universe.code))).all())
    agents = list((await session.scalars(select(Agent).order_by(Agent.code))).all())
    position = int(await session.scalar(select(func.max(Chronicle.position))) or 0)

    return {
        "position": position,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "missions": [
            {
                "id": mission.id,
                "title": mission.title,
                "objective": mission.objective,
                "status": mission.status,
                "started_at": mission.started_at.isoformat() if mission.started_at else None,
                "completed_at": mission.completed_at.isoformat() if mission.completed_at else None,
            }
            for mission in missions
        ],
        "tasks": [
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
        ],
        "universes": [
            {"id": universe.id, "code": universe.code, "name": universe.name, "active": universe.active}
            for universe in universes
        ],
        "agents": [
            {
                "id": agent.id,
                "code": agent.code,
                "name": agent.name,
                "universe_id": agent.universe_id,
                "active": agent.active,
            }
            for agent in agents
        ],
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
