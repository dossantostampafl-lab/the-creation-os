import asyncio
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.agents.handlers import ExecutionContext, HandlerError, HandlerRegistry, default_registry
from app.agents.state_machine import TERMINAL_STATES, ExecutionState, transition_execution
from app.core.domain import AuthorizationDenied, DomainError
from app.models.dispatch import Worker
from app.models.execution import AgentExecution, AgentExecutionEvent
from app.repositories.conscious_memory import ConsciousMemoryRepository
from app.repositories.execution import ExecutionRepository
from app.services.conscious_memory import ConsciousMemoryService
from app.services.dispatch import DispatchService
from app.services.domain import NotFoundError

# Capabilities that receive resolved Conscious Memory context in their payload
# before invocation (Lote 2.5, section 2, pattern (a) — "resolucao previa"):
# the worker/service layer queries memory *outside* the handler and injects
# already-materialized data, not a connection. ExecutionContext itself never
# gains a database session — the frozen v0.4.5 Handler Registry contract is
# unchanged; only the plain-dict payload handlers already receive (the same
# vehicle Task.input_json already uses, opened up in Lote 2.6) gets richer.
MEMORY_AUGMENTED_CAPABILITIES = {"knowledge_research"}
MEMORY_CONTEXT_LIMIT = 3


class ExecutionError(DomainError):
    pass


class AgentExecutionService:
    def __init__(
        self,
        repository: ExecutionRepository,
        dispatch: DispatchService,
        registry: HandlerRegistry = default_registry,
        retry_base_seconds: int = 30,
        retry_maximum_seconds: int = 3600,
    ):
        self.repository = repository
        self.dispatch = dispatch
        self.registry = registry
        # Defaults match DispatchService.fail()'s own defaults exactly, so
        # behavior is unchanged for every caller that doesn't override them.
        # app/worker.py passes explicit values sourced from environment
        # variables so integration tests can exercise real (not zeroed)
        # retry/backoff timing practically. See ARCHITECTURE.md, Lote: P4/P5
        # — concorrência real de worker.
        self.retry_base_seconds = retry_base_seconds
        self.retry_maximum_seconds = retry_maximum_seconds

    async def _event(self, execution, event_type, worker, metadata=None):
        await self.repository.add(
            AgentExecutionEvent(
                execution_id=execution.id,
                sequence=await self.repository.next_event_sequence(execution.id),
                event_type=event_type,
                actor_type="worker",
                actor_id=worker.worker_uuid,
                metadata_json=metadata or {},
            )
        )

    async def _chain(self, worker: Worker, dispatch_id: str, token: str, handler_name: str, handler_version: str):
        item = await self.dispatch._leased(dispatch_id, worker.worker_uuid, token)
        mission = await self.repository.mission(item.mission_id)
        task = await self.repository.task(item.task_id)
        agent = await self.repository.agent(item.agent_id) if item.agent_id else None
        capability = await self.repository.capability(item.capability_id) if item.capability_id else None
        if mission is None or mission.status not in {"authorized", "distributed", "executing"}:
            raise AuthorizationDenied("Mission is not authorized")
        if task is None or task.mission_id != mission.id or task.state != "ready":
            raise AuthorizationDenied("Task is not executable")
        if agent is None or not agent.enabled or agent.status != "idle":
            raise AuthorizationDenied("Agent is not eligible")
        if capability is None or not await self.repository.agent_has_capability(agent.id, capability.id):
            raise AuthorizationDenied("Agent capability is invalid")
        if capability.id not in {entry.id for entry in worker.capabilities}:
            raise AuthorizationDenied("Worker capability is invalid")
        handler = self.registry.resolve(handler_name, handler_version, capability.name)
        return item, mission, task, agent, capability, handler

    async def create(self, worker: Worker, dispatch_id: str, token: str, handler_name: str, handler_version: str):
        item, mission, task, agent, capability, handler = await self._chain(
            worker, dispatch_id, token, handler_name, handler_version
        )
        now = datetime.now(timezone.utc)
        deadline = item.lease_expires_at
        if deadline is None:
            raise ExecutionError("Execution deadline is missing")
        aware_deadline = deadline if deadline.tzinfo else deadline.replace(tzinfo=timezone.utc)
        remaining = int((aware_deadline - now).total_seconds())
        max_duration = min(task.timeout_seconds, handler.timeout_seconds, remaining)
        if max_duration < 1:
            raise ExecutionError("Execution deadline expired")

        # (dispatch_item_id, attempt_number) is UNIQUE (uq_execution_dispatch_attempt),
        # and lease reclaim (DispatchService.lease()'s expired-lease sweep) does not
        # bump attempt_count — a worker that dies after create() but before
        # acknowledge()/fail() leaves this exact (item, attempt_number) pair already
        # occupied by an abandoned row. `_chain()` above already proved `worker`/`token`
        # holds the item's *current* lease, so an existing row here with a different
        # worker_id is provably that abandoned attempt, not a live one — resume it
        # (preserving its original id/created_at/prior events for the audit trail)
        # instead of inserting a second row for the same key, which would always
        # fail. Confirmed by direct reproduction with two real `python -m app.worker`
        # processes; see ARCHITECTURE.md, Lote: P4/P5 — concorrência real de worker.
        existing = await self.repository.for_attempt(item.id, item.attempt_count, lock=True)
        if existing is not None and existing.worker_id != worker.id:
            existing.worker_id = worker.id
            existing.agent_id = agent.id
            existing.capability_id = capability.id
            existing.handler_name = handler.name
            existing.handler_version = handler.version
            existing.state = "pending"
            existing.input_payload = task.input_json
            existing.deadline = aware_deadline
            existing.max_duration_seconds = max_duration
            existing.version += 1
            # Dedicated event_type — distinct from "execution_created" (the
            # normal, first-attempt path below) — so consumers can tell a
            # resumed/reclaimed attempt apart from a fresh one.
            # ck_execution_event_type (migration 0027_execution_reclaimed_event)
            # was extended specifically for this; see ARCHITECTURE.md, Lote:
            # event_type dedicado para reclaim de lease.
            await self._event(existing, "execution_reclaimed", worker)
            await self.repository.commit()
            return existing

        execution = AgentExecution(
            dispatch_item_id=item.id,
            mission_id=mission.id,
            task_id=task.id,
            agent_id=agent.id,
            worker_id=worker.id,
            capability_id=capability.id,
            attempt_number=item.attempt_count,
            handler_name=handler.name,
            handler_version=handler.version,
            state="pending",
            input_payload=task.input_json,
            contract_json={
                "input_schema_version": "1.0",
                "output_schema_version": "1.0",
                "metadata": {},
            },
            deadline=aware_deadline,
            max_duration_seconds=max_duration,
            version=1,
        )
        try:
            await self.repository.add(execution)
            await self._event(execution, "execution_created", worker)
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.session.rollback()
            raise ExecutionError("Execution already exists for this dispatch attempt") from exc
        return execution

    async def _owned(self, execution_id: str, worker: Worker, token: str):
        execution = await self.repository.get(execution_id, lock=True)
        if execution is None:
            raise NotFoundError("Execution not found")
        if execution.worker_id != worker.id:
            raise AuthorizationDenied("Execution belongs to another worker")
        await self.dispatch._leased(execution.dispatch_item_id, worker.worker_uuid, token)
        return execution

    async def accept(self, execution_id: str, worker: Worker, token: str):
        execution = await self._owned(execution_id, worker, token)
        execution.state = transition_execution(execution.state, ExecutionState.ACCEPTED)
        execution.version += 1
        await self._event(execution, "execution_accepted", worker)
        await self.repository.commit()
        return execution

    async def _resolve_memory_context(self, topic: str) -> list[str]:
        """Pattern (a): search Conscious Memory for prior knowledge related to
        this task's topic, fully materialized here (a list of strings), before
        the handler ever runs. The handler receives plain data in its payload,
        never a repository, session, or MemoryStore instance."""
        service = ConsciousMemoryService(ConsciousMemoryRepository(self.repository.session))
        matches = await service.search(topic, limit=MEMORY_CONTEXT_LIMIT)
        return [f"[conscious-memory:{item.id}] {item.content}" for item in matches]

    async def run(self, execution_id: str, worker: Worker, token: str):
        execution = await self._owned(execution_id, worker, token)
        capability_name = await self._capability_name(execution)
        handler = self.registry.resolve(execution.handler_name, execution.handler_version, capability_name)
        execution.state = transition_execution(execution.state, ExecutionState.RUNNING)
        execution.started_at = datetime.now(timezone.utc)
        execution.version += 1
        await self._event(execution, "execution_started", worker)
        await self.repository.commit()
        context = ExecutionContext(
            execution_id=execution.id,
            mission_id=execution.mission_id,
            task_id=execution.task_id,
            agent_id=execution.agent_id,
            capability_id=execution.capability_id,
            deadline=execution.deadline,
        )
        payload = dict(execution.input_payload)
        if capability_name in MEMORY_AUGMENTED_CAPABILITIES:
            memory_context = await self._resolve_memory_context(str(payload.get("topic", "")))
            if memory_context:
                payload["notes"] = [*payload.get("notes", []), *memory_context]
        try:
            async with asyncio.timeout(execution.max_duration_seconds):
                result = await self.registry.invoke(handler, context, payload)
            if result.status != "succeeded":
                raise HandlerError("Handler returned failure")
        except TimeoutError:
            return await self._finish_failure(execution.id, worker, token, ExecutionState.TIMED_OUT, "EXECUTION_TIMEOUT")
        except Exception:
            return await self._finish_failure(execution.id, worker, token, ExecutionState.FAILED, "HANDLER_FAILED")
        execution = await self.repository.get(execution.id, lock=True)
        if execution is None:
            raise NotFoundError("Execution not found")
        execution.state = transition_execution(execution.state, ExecutionState.SUCCEEDED)
        execution.output_payload = result.output
        execution.result_metrics = result.metrics
        execution.result_warnings = result.warnings
        execution.finished_at = datetime.now(timezone.utc)
        execution.version += 1
        await self._event(execution, "execution_succeeded", worker)
        await self._event(execution, "result_returned", worker, {"target": "tree_core"})
        worker.status = "available"
        await self.dispatch.acknowledge(execution.dispatch_item_id, worker.worker_uuid, token)
        return execution

    async def _capability_name(self, execution):
        capability = await self.repository.capability(execution.capability_id)
        if capability is None:
            raise ExecutionError("Execution capability is missing")
        return capability.name

    async def _finish_failure(self, execution_id, worker, token, state, code):
        execution = await self.repository.get(execution_id, lock=True)
        if execution is None:
            raise NotFoundError("Execution not found")
        execution.state = transition_execution(execution.state, state)
        execution.error_code = code
        execution.error_message = "Controlled Agent execution failed"
        execution.finished_at = datetime.now(timezone.utc)
        execution.version += 1
        event = "execution_timed_out" if state == ExecutionState.TIMED_OUT else "execution_failed"
        await self._event(execution, event, worker, {"error_code": code})
        await self._event(execution, "result_returned", worker, {"target": "tree_core", "error_code": code})
        worker.status = "available"
        await self.dispatch.fail(
            execution.dispatch_item_id, worker.worker_uuid, token, code, "Controlled execution failure",
            base=self.retry_base_seconds, maximum=self.retry_maximum_seconds,
        )
        return execution

    async def cancel(self, execution_id: str, worker: Worker, token: str):
        execution = await self._owned(execution_id, worker, token)
        execution.state = transition_execution(execution.state, ExecutionState.CANCELLED)
        execution.finished_at = datetime.now(timezone.utc)
        execution.version += 1
        await self._event(execution, "execution_cancelled", worker)
        await self._event(execution, "result_returned", worker, {"target": "tree_core"})
        worker.status = "available"
        await self.dispatch.release(execution.dispatch_item_id, worker.worker_uuid, token)
        return execution

    async def get(self, execution_id: str):
        execution = await self.repository.get(execution_id)
        if execution is None:
            raise NotFoundError("Execution not found")
        return execution

    async def result(self, execution_id: str):
        execution = await self.get(execution_id)
        if ExecutionState(execution.state) not in TERMINAL_STATES:
            raise ExecutionError("Execution result is not terminal")
        return execution
