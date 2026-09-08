from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.capabilities.contracts import CapabilityIntent, CapabilityResult, IdempotencyClass, MissionAuthorization
from app.capabilities.gateway import CapabilityGateway
from app.capabilities.policy import CapabilityDenied, authorize_capability
from app.models.execution import CapabilityInvocation


class CapabilityRuntime:
    """Execute capabilities with a durable authorization record and no DB transaction across adapter work."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], gateway: CapabilityGateway) -> None:
        self.session_factory = session_factory
        self.gateway = gateway

    async def execute(
        self,
        *,
        mission_id: str,
        task_id: str | None,
        agent_execution_id: str | None,
        intent: CapabilityIntent,
        authorization: MissionAuthorization,
    ) -> CapabilityResult:
        try:
            authorize_capability(intent, authorization)
        except CapabilityDenied as exc:
            async with self.session_factory() as session:
                session.add(self._invocation(
                    mission_id=mission_id,
                    task_id=task_id,
                    agent_execution_id=agent_execution_id,
                    intent=intent,
                    authorization=authorization,
                    status="DENIED",
                    error={"code": "CAPABILITY_DENIED", "detail": str(exc)},
                    completed=True,
                ))
                await session.commit()
            raise

        async with self.session_factory() as session:
            authorized_invocation = self._invocation(
                mission_id=mission_id,
                task_id=task_id,
                agent_execution_id=agent_execution_id,
                intent=intent,
                authorization=authorization,
                status="AUTHORIZED",
            )
            session.add(authorized_invocation)
            await session.flush()
            invocation_id = authorized_invocation.id
            await session.commit()

        try:
            result = await self.gateway.execute(intent, authorization)
        except Exception as exc:
            status = "UNCERTAIN" if intent.idempotency_class is IdempotencyClass.AT_MOST_ONCE else "FAILED"
            async with self.session_factory() as session:
                failed_invocation = await session.get(CapabilityInvocation, invocation_id, with_for_update=True)
                if failed_invocation is None:
                    raise RuntimeError("capability invocation record disappeared") from exc
                failed_invocation.status = status
                failed_invocation.error_json = {"code": "CAPABILITY_EXECUTION_FAILED", "detail": exc.__class__.__name__}
                failed_invocation.completed_at = datetime.now(timezone.utc)
                await session.commit()
            raise

        async with self.session_factory() as session:
            completed_invocation = await session.get(CapabilityInvocation, invocation_id, with_for_update=True)
            if completed_invocation is None:
                raise RuntimeError("capability invocation record disappeared")
            completed_invocation.status = "SUCCEEDED" if result.ok else "FAILED"
            completed_invocation.result_json = result.model_dump(mode="json")
            completed_invocation.error_json = result.error if not result.ok else {}
            completed_invocation.completed_at = datetime.now(timezone.utc)
            await session.commit()
        return result

    @staticmethod
    def _invocation(
        *,
        mission_id: str,
        task_id: str | None,
        agent_execution_id: str | None,
        intent: CapabilityIntent,
        authorization: MissionAuthorization,
        status: str,
        error: dict | None = None,
        completed: bool = False,
    ) -> CapabilityInvocation:
        return CapabilityInvocation(
            mission_id=mission_id,
            task_id=task_id,
            agent_execution_id=agent_execution_id,
            capability=intent.capability,
            action=intent.action,
            resource=intent.resource,
            external_effect=intent.external_effect,
            idempotency_class=intent.idempotency_class.value,
            idempotency_key=intent.idempotency_key,
            authorization_version=authorization.version,
            status=status,
            request_json=intent.model_dump(mode="json"),
            result_json={},
            error_json=error or {},
            completed_at=datetime.now(timezone.utc) if completed else None,
        )
