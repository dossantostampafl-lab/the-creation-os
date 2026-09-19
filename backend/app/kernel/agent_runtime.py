from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.capabilities.contracts import CapabilityIntent, MissionAuthorization
from app.capabilities.runtime import CapabilityRuntime
from app.inference.contracts import InferenceRequest, ModelRequirements, ProviderUnavailable
from app.inference.router import ModelRouter
from app.kernel.completion_engine import MissionCompletionEngine
from app.kernel.orchestrator import claim_next_ready_task, finish_task_attempt
from app.models.entities import Agent, Mission


class AgentRuntime:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        router: ModelRouter,
        capability_runtime: CapabilityRuntime | None = None,
        completion_engine: MissionCompletionEngine | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.router = router
        self.capability_runtime = capability_runtime
        self.completion_engine = completion_engine

    async def run_next(self, mission_id: str, correlation_id: str | None = None) -> bool:
        async with self.session_factory() as session:
            claimed = await claim_next_ready_task(session, mission_id)
            if claimed is None:
                await session.commit()
                return False
            task, execution = claimed
            agent = await session.get(Agent, task.agent_id)
            mission = await session.get(Mission, mission_id)
            if agent is None or not agent.active:
                await session.rollback()
                raise ValueError("active Agent not found for claimed Task")
            if mission is None:
                await session.rollback()
                raise ValueError("Mission not found for claimed Task")
            task_id = task.id
            execution_id = execution.id
            input_payload = dict(task.input_json or {})
            capabilities = dict(agent.capabilities_json or {})
            creator_id = mission.creator_id
            mission_correlation_id = correlation_id or str(
                (mission.authorization_json or {}).get("correlation_id") or uuid.uuid4()
            )
            await session.commit()

        preferred_provider = capabilities.get("inference_provider")
        fallback_providers = list(capabilities.get("fallback_providers", []))
        model = capabilities.get("model")
        if not preferred_provider:
            await self._finish_failure(
                mission_id,
                mission_correlation_id,
                task_id,
                execution_id,
                {"code": "PROVIDER_UNAVAILABLE", "detail": "Agent has no inference_provider"},
            )
            return True

        request = InferenceRequest(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Execute the authorized task within its supplied scope. "
                        "Do not perform external actions directly. If a capability is needed, emit a normalized "
                        "capability_intent through the provider tool-call metadata."
                    ),
                },
                {"role": "user", "content": self._render_task(input_payload)},
            ],
            model=model,
            requirements=ModelRequirements(
                preferred_provider=str(preferred_provider),
                fallback_providers=[str(name) for name in fallback_providers],
            ),
            metadata={
                "task_id": task_id,
                "mission_id": mission_id,
                "creator_id": creator_id,
                "enable_capability_intents": self.capability_runtime is not None,
                "cache_policy": "bypass",
                "cache_intent": "SYSTEM_COMMAND",
                "cache_sensitivity": "PRIVATE",
                "tool_state_class": "action_capable",
            },
        )

        try:
            response = await self.router.generate(request)
        except ProviderUnavailable as exc:
            await self._finish_failure(
                mission_id,
                mission_correlation_id,
                task_id,
                execution_id,
                {"code": exc.code, "provider": exc.provider, "detail": str(exc)},
            )
            return True
        except Exception as exc:
            await self._finish_failure(
                mission_id,
                mission_correlation_id,
                task_id,
                execution_id,
                {"code": "INFERENCE_ERROR", "detail": exc.__class__.__name__},
            )
            return True

        output: dict[str, Any]
        capability_payload = response.metadata.get("capability_intent")
        if capability_payload is not None:
            if self.capability_runtime is None:
                await self._finish_failure(
                    mission_id,
                    mission_correlation_id,
                    task_id,
                    execution_id,
                    {"code": "CAPABILITY_GATEWAY_UNAVAILABLE"},
                )
                return True
            try:
                intent = CapabilityIntent.model_validate(capability_payload)
                authorization = await self._mission_authorization(mission_id)
                capability_result = await self.capability_runtime.execute(
                    mission_id=mission_id,
                    task_id=task_id,
                    agent_execution_id=execution_id,
                    intent=intent,
                    authorization=authorization,
                )
            except Exception as exc:
                await self._finish_failure(
                    mission_id,
                    mission_correlation_id,
                    task_id,
                    execution_id,
                    {"code": "CAPABILITY_EXECUTION_REJECTED", "detail": exc.__class__.__name__},
                )
                return True
            if not capability_result.ok:
                await self._finish_failure(
                    mission_id,
                    mission_correlation_id,
                    task_id,
                    execution_id,
                    {
                        "code": "CAPABILITY_RESULT_FAILED",
                        "capability": intent.capability,
                        "action": intent.action,
                    },
                    terminal=True,
                )
                return True
            output = {
                "content": response.content,
                "capability_result": capability_result.model_dump(mode="json"),
            }
        else:
            output = {"content": response.content, "metadata": response.metadata}

        async with self.session_factory() as session:
            await finish_task_attempt(
                session,
                task_id=task_id,
                execution_id=execution_id,
                succeeded=True,
                output=output,
                provider=response.provider,
                model=response.model,
            )
            await session.commit()
        await self._evaluate_completion(mission_id, mission_correlation_id)
        return True

    async def _mission_authorization(self, mission_id: str) -> MissionAuthorization:
        async with self.session_factory() as session:
            mission = await session.get(Mission, mission_id)
            if mission is None:
                raise ValueError("Mission not found")
            payload = dict(mission.authorization_json or {})
        return MissionAuthorization.model_validate(payload)

    async def _finish_failure(
        self,
        mission_id: str,
        correlation_id: str,
        task_id: str,
        execution_id: str,
        error: dict[str, Any],
        *,
        terminal: bool = False,
    ) -> None:
        async with self.session_factory() as session:
            await finish_task_attempt(
                session,
                task_id=task_id,
                execution_id=execution_id,
                succeeded=False,
                error=error,
                terminal_failure=terminal,
            )
            await session.commit()
        await self._evaluate_completion(mission_id, correlation_id)

    async def _evaluate_completion(self, mission_id: str, correlation_id: str) -> None:
        if self.completion_engine is not None:
            await self.completion_engine.evaluate(mission_id, correlation_id)

    @staticmethod
    def _render_task(payload: dict[str, Any]) -> str:
        objective = payload.get("mission_objective", "")
        description = payload.get("description", "")
        criteria = payload.get("completion_criteria", {})
        return f"Mission objective: {objective}\nTask: {description}\nCompletion criteria: {criteria}"
