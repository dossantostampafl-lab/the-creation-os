from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Mission, MissionStep, Task
from app.models.execution import AgentExecution

TERMINAL_TASK_STATES = {"SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED"}
FAILED_DEPENDENCY_STATES = {"FAILED", "BLOCKED", "CANCELLED"}


async def refresh_task_readiness(session: AsyncSession, mission_id: str) -> None:
    tasks = list((await session.scalars(
        select(Task).where(Task.mission_id == mission_id).order_by(Task.created_at)
    )).all())
    if not tasks:
        return
    steps = list((await session.scalars(
        select(MissionStep).where(MissionStep.id.in_([task.step_id for task in tasks]))
    )).all())
    step_by_id = {step.id: step for step in steps}
    task_by_step_key = {step_by_id[task.step_id].step_key: task for task in tasks}

    for task in tasks:
        if task.status != "PENDING":
            continue
        step = step_by_id[task.step_id]
        dependencies = list(step.depends_on_json or [])
        dependency_tasks = [task_by_step_key[key] for key in dependencies if key in task_by_step_key]
        if len(dependency_tasks) != len(dependencies):
            task.status = "BLOCKED"
            task.error_json = {"code": "DEPENDENCY_MISSING"}
            continue
        if any(dep.status in FAILED_DEPENDENCY_STATES for dep in dependency_tasks):
            task.status = "BLOCKED"
            task.error_json = {"code": "DEPENDENCY_FAILED"}
            continue
        if all(dep.status == "SUCCEEDED" for dep in dependency_tasks):
            task.status = "READY"

    await session.flush()


async def _cancel_remaining_tasks(session: AsyncSession, mission_id: str) -> None:
    now = datetime.now(timezone.utc)
    tasks = list((await session.scalars(
        select(Task).where(Task.mission_id == mission_id).with_for_update()
    )).all())
    for task in tasks:
        if task.status in TERMINAL_TASK_STATES:
            continue
        task.status = "CANCELLED"
        task.error_json = {"code": "MISSION_CANCELLED"}
        task.completed_at = now
    await session.flush()


async def claim_next_ready_task(session: AsyncSession, mission_id: str) -> tuple[Task, AgentExecution] | None:
    mission = await session.scalar(
        select(Mission).where(Mission.id == mission_id).with_for_update()
    )
    if mission is None:
        raise ValueError("Mission not found")
    if mission.status == "cancelled":
        await _cancel_remaining_tasks(session, mission_id)
        return None
    if mission.status != "executing":
        return None

    await refresh_task_readiness(session, mission_id)
    task = await session.scalar(
        select(Task)
        .where(Task.mission_id == mission_id, Task.status == "READY")
        .order_by(Task.created_at, Task.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if task is None:
        return None
    if task.attempt_count >= task.max_attempts:
        task.status = "FAILED"
        task.error_json = {"code": "MAX_ATTEMPTS_EXCEEDED"}
        task.completed_at = datetime.now(timezone.utc)
        await session.flush()
        return None

    task.attempt_count += 1
    task.status = "RUNNING"
    task.started_at = task.started_at or datetime.now(timezone.utc)
    execution = AgentExecution(
        task_id=task.id,
        agent_id=task.agent_id,
        attempt=task.attempt_count,
        status="RUNNING",
        input_json=dict(task.input_json or {}),
        output_json={},
        error_json={},
    )
    session.add(execution)
    await session.flush()
    return task, execution


async def finish_task_attempt(
    session: AsyncSession,
    *,
    task_id: str,
    execution_id: str,
    succeeded: bool,
    output: dict | None = None,
    error: dict | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> Task:
    task = await session.get(Task, task_id, with_for_update=True)
    execution = await session.get(AgentExecution, execution_id, with_for_update=True)
    if task is None or execution is None or execution.task_id != task_id:
        raise ValueError("task execution attempt not found")
    if task.status != "RUNNING" or execution.status != "RUNNING":
        raise ValueError("task execution attempt is not running")

    now = datetime.now(timezone.utc)
    execution.provider = provider
    execution.model = model
    execution.completed_at = now
    if succeeded:
        task.status = "SUCCEEDED"
        task.output_json = output or {}
        task.error_json = {}
        execution.status = "SUCCEEDED"
        execution.output_json = output or {}
        execution.error_json = {}
    else:
        failure = error or {"code": "EXECUTION_FAILED"}
        task.error_json = failure
        execution.status = "FAILED"
        execution.error_json = failure
        if task.attempt_count < task.max_attempts:
            task.status = "READY"
        else:
            task.status = "FAILED"
            task.completed_at = now

    if succeeded:
        task.completed_at = now

    await session.flush()
    await refresh_task_readiness(session, task.mission_id)
    return task
