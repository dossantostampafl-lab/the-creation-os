from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.entities import Task
from app.models.execution import AgentExecution, CapabilityInvocation
from app.repositories.domain import DomainRepository


class ExecutionReconciler:
    """Recover durable execution state after process interruption without replaying uncertain effects."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def reconcile(self, correlation_id: str) -> dict[str, int]:
        counts = {"retried_tasks": 0, "failed_tasks": 0, "blocked_tasks": 0, "uncertain_capabilities": 0}
        async with self.session_factory() as session:
            repository = DomainRepository(session)
            running = list((await session.scalars(
                select(AgentExecution).where(AgentExecution.status == "RUNNING").with_for_update(skip_locked=True)
            )).all())

            for execution in running:
                task = await session.get(Task, execution.task_id, with_for_update=True)
                if task is None:
                    execution.status = "FAILED"
                    execution.error_json = {"code": "TASK_MISSING_DURING_RECONCILIATION"}
                    execution.completed_at = datetime.now(timezone.utc)
                    continue

                uncertain = list((await session.scalars(
                    select(CapabilityInvocation).where(
                        CapabilityInvocation.agent_execution_id == execution.id,
                        CapabilityInvocation.status == "AUTHORIZED",
                    ).with_for_update(skip_locked=True)
                )).all())
                has_uncertain_at_most_once = False
                for invocation in uncertain:
                    if invocation.idempotency_class == "AT_MOST_ONCE":
                        invocation.status = "UNCERTAIN"
                        invocation.error_json = {"code": "INTERRUPTED_AT_MOST_ONCE_EFFECT"}
                        invocation.completed_at = datetime.now(timezone.utc)
                        counts["uncertain_capabilities"] += 1
                        has_uncertain_at_most_once = True
                    else:
                        invocation.status = "FAILED"
                        invocation.error_json = {"code": "INTERRUPTED_RETRYABLE_EFFECT"}
                        invocation.completed_at = datetime.now(timezone.utc)

                execution.status = "FAILED"
                execution.error_json = {"code": "INTERRUPTED_BY_RESTART"}
                execution.completed_at = datetime.now(timezone.utc)

                if has_uncertain_at_most_once:
                    task.status = "BLOCKED"
                    task.error_json = {"code": "AT_MOST_ONCE_RECONCILIATION_REQUIRED"}
                    counts["blocked_tasks"] += 1
                elif task.attempt_count < task.max_attempts:
                    task.status = "READY"
                    task.error_json = {"code": "INTERRUPTED_BY_RESTART"}
                    counts["retried_tasks"] += 1
                else:
                    task.status = "FAILED"
                    task.error_json = {"code": "MAX_ATTEMPTS_EXCEEDED_AFTER_RESTART"}
                    task.completed_at = datetime.now(timezone.utc)
                    counts["failed_tasks"] += 1

                await repository.add_event(
                    "task_execution_reconciled",
                    "task",
                    task.id,
                    "system",
                    "execution_reconciler",
                    correlation_id,
                    {"task_status": task.status, "execution_id": execution.id},
                )

            await repository.commit()
        return counts
