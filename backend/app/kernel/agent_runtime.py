from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.inference.contracts import InferenceRequest, ModelRequirements, ProviderUnavailable
from app.inference.router import ModelRouter
from app.kernel.orchestrator import claim_next_ready_task, finish_task_attempt
from app.models.entities import Agent


class AgentRuntime:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], router: ModelRouter) -> None:
        self.session_factory = session_factory
        self.router = router

    async def run_next(self, mission_id: str) -> bool:
        async with self.session_factory() as session:
            claimed = await claim_next_ready_task(session, mission_id)
            if claimed is None:
                await session.commit()
                return False
            task, execution = claimed
            agent = await session.get(Agent, task.agent_id)
            if agent is None or not agent.active:
                await session.rollback()
                raise ValueError("active Agent not found for claimed Task")
            task_id = task.id
            execution_id = execution.id
            input_payload = dict(task.input_json or {})
            capabilities = dict(agent.capabilities_json or {})
            await session.commit()

        preferred_provider = capabilities.get("inference_provider")
        fallback_providers = list(capabilities.get("fallback_providers", []))
        model = capabilities.get("model")
        if not preferred_provider:
            await self._finish_failure(
                task_id,
                execution_id,
                {"code": "PROVIDER_UNAVAILABLE", "detail": "Agent has no inference_provider"},
            )
            return True

        request = InferenceRequest(
            messages=[
                {
                    "role": "system",
                    "content": "Execute the authorized task within its supplied scope. Return only the task result.",
                },
                {"role": "user", "content": self._render_task(input_payload)},
            ],
            model=model,
            requirements=ModelRequirements(
                preferred_provider=str(preferred_provider),
                fallback_providers=[str(name) for name in fallback_providers],
            ),
            metadata={"task_id": task_id, "mission_id": mission_id},
        )

        try:
            response = await self.router.generate(request)
        except ProviderUnavailable as exc:
            await self._finish_failure(
                task_id,
                execution_id,
                {"code": exc.code, "provider": exc.provider, "detail": str(exc)},
            )
            return True
        except Exception as exc:
            await self._finish_failure(
                task_id,
                execution_id,
                {"code": "INFERENCE_ERROR", "detail": exc.__class__.__name__},
            )
            return True

        async with self.session_factory() as session:
            await finish_task_attempt(
                session,
                task_id=task_id,
                execution_id=execution_id,
                succeeded=True,
                output={"content": response.content, "metadata": response.metadata},
                provider=response.provider,
                model=response.model,
            )
            await session.commit()
        return True

    async def _finish_failure(self, task_id: str, execution_id: str, error: dict[str, Any]) -> None:
        async with self.session_factory() as session:
            await finish_task_attempt(
                session,
                task_id=task_id,
                execution_id=execution_id,
                succeeded=False,
                error=error,
            )
            await session.commit()

    @staticmethod
    def _render_task(payload: dict[str, Any]) -> str:
        objective = payload.get("mission_objective", "")
        description = payload.get("description", "")
        criteria = payload.get("completion_criteria", {})
        return f"Mission objective: {objective}\nTask: {description}\nCompletion criteria: {criteria}"
