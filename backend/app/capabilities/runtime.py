from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.capabilities.contracts import (
    CapabilityContext,
    CapabilityIntent,
    CapabilityResult,
    IdempotencyClass,
    MissionAuthorization,
)
from app.capabilities.gateway import CapabilityGateway
from app.capabilities.policy import (
    CapabilityDenied,
    authorize_capability,
    effective_idempotency_class,
)
from app.config import settings
from app.models.entities import Mission, Task
from app.models.execution import CapabilityInvocation
from app.repositories.domain import DomainRepository
from app.services.economy import (
    EconomicPolicyError,
    mark_capability_committed,
    mark_capability_settling,
    mark_capability_uncertain,
    reserve_for_capability,
    settle_capability_result,
)


@dataclass(frozen=True)
class _EconomicExecution:
    creator_id: str
    universe_id: str
    mission_id: str
    opportunity_id: str | None
    amount: Decimal
    currency: str
    external_reference: str
    correlation_id: str


class CapabilityRuntime:
    """Execute capabilities with durable authorization, economic gates, and no DB transaction across adapter work."""

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
        declaration = self.gateway.declaration(intent.capability)
        effective_idempotency = effective_idempotency_class(intent, declaration)
        try:
            authorize_capability(intent, authorization, declaration)
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

        economic: _EconomicExecution | None = None
        try:
            economic = await self._prepare_economic_execution(
                mission_id=mission_id,
                task_id=task_id,
                invocation_id=invocation_id,
                intent=intent,
                has_external_effect=declaration.external_effect or intent.external_effect,
            )
        except Exception as exc:
            async with self.session_factory() as session:
                invocation = await session.get(CapabilityInvocation, invocation_id, with_for_update=True)
                if invocation is None:
                    raise RuntimeError("capability invocation record disappeared") from exc
                invocation.status = "DENIED"
                invocation.error_json = {
                    "code": "ECONOMIC_POLICY_DENIED",
                    "detail": str(exc) if isinstance(exc, EconomicPolicyError) else exc.__class__.__name__,
                }
                invocation.completed_at = datetime.now(timezone.utc)
                await session.commit()
            raise

        try:
            context = CapabilityContext(
                mission_id=mission_id,
                task_id=task_id,
                authorization=authorization,
            )
            result = await self.gateway.execute(intent, context)
        except Exception as exc:
            status = "UNCERTAIN" if effective_idempotency is IdempotencyClass.AT_MOST_ONCE else "FAILED"
            if economic is not None:
                async with self.session_factory() as session:
                    repository = DomainRepository(session)
                    if status == "UNCERTAIN":
                        await mark_capability_uncertain(
                            repository,
                            creator_id=economic.creator_id,
                            universe_id=economic.universe_id,
                            mission_id=economic.mission_id,
                            opportunity_id=economic.opportunity_id,
                            amount=economic.amount,
                            currency=economic.currency,
                            external_reference=economic.external_reference,
                            correlation_id=economic.correlation_id,
                        )
                    else:
                        await settle_capability_result(
                            repository,
                            creator_id=economic.creator_id,
                            universe_id=economic.universe_id,
                            mission_id=economic.mission_id,
                            opportunity_id=economic.opportunity_id,
                            amount=economic.amount,
                            currency=economic.currency,
                            external_reference=economic.external_reference,
                            correlation_id=economic.correlation_id,
                        )

            async with self.session_factory() as session:
                failed_invocation = await session.get(CapabilityInvocation, invocation_id, with_for_update=True)
                if failed_invocation is None:
                    raise RuntimeError("capability invocation record disappeared") from exc
                failed_invocation.status = status
                failed_invocation.error_json = {
                    "code": "CAPABILITY_EXECUTION_FAILED",
                    "detail": exc.__class__.__name__,
                }
                failed_invocation.completed_at = datetime.now(timezone.utc)
                await session.commit()
            raise

        if economic is not None:
            pnl = self._confirmed_pnl(result)
            async with self.session_factory() as session:
                await settle_capability_result(
                    DomainRepository(session),
                    creator_id=economic.creator_id,
                    universe_id=economic.universe_id,
                    mission_id=economic.mission_id,
                    opportunity_id=economic.opportunity_id,
                    amount=economic.amount,
                    currency=economic.currency,
                    external_reference=economic.external_reference,
                    pnl=pnl,
                    correlation_id=economic.correlation_id,
                )

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

    async def _prepare_economic_execution(
        self,
        *,
        mission_id: str,
        task_id: str | None,
        invocation_id: str,
        intent: CapabilityIntent,
        has_external_effect: bool,
    ) -> _EconomicExecution | None:
        economic = intent.economic or {}
        if not economic or not has_external_effect:
            return None
        raw_amount = economic.get("max_spend")
        if raw_amount is None:
            return None
        amount = abs(Decimal(str(raw_amount)))
        if amount == 0:
            return None

        async with self.session_factory() as session:
            mission = await session.get(Mission, mission_id)
            if mission is None:
                raise EconomicPolicyError("Mission not found for economic capability")

            task = await session.get(Task, task_id) if task_id is not None else None
            if task is not None and task.mission_id != mission.id:
                raise EconomicPolicyError("Task is outside the economic Mission")

            requested_universe = economic.get("universe_id")
            universe_id = task.universe_id if task is not None else str(requested_universe or "")
            if not universe_id:
                raise EconomicPolicyError("economic capability requires a Universe")
            if requested_universe is not None and str(requested_universe) != universe_id:
                raise EconomicPolicyError("economic Universe does not match the executing Task")

            requested_opportunity = economic.get("opportunity_id")
            if requested_opportunity is not None and str(requested_opportunity) != str(mission.opportunity_id or ""):
                raise EconomicPolicyError("economic Opportunity does not match the Mission")

            currency = str(economic.get("currency") or settings.economic_currency).upper()
            external_reference = intent.idempotency_key or invocation_id
            context = _EconomicExecution(
                creator_id=mission.creator_id,
                universe_id=universe_id,
                mission_id=mission.id,
                opportunity_id=mission.opportunity_id,
                amount=amount,
                currency=currency,
                external_reference=external_reference,
                correlation_id=invocation_id,
            )
            repository = DomainRepository(session)
            metadata: dict[str, Any] = {
                "capability": intent.capability,
                "action": intent.action,
                "estimated_risk": economic.get("estimated_risk"),
                "idempotency_key": intent.idempotency_key,
            }
            await reserve_for_capability(
                repository,
                creator_id=context.creator_id,
                universe_id=context.universe_id,
                mission_id=context.mission_id,
                opportunity_id=context.opportunity_id,
                amount=context.amount,
                currency=context.currency,
                external_reference=context.external_reference,
                metadata=metadata,
                correlation_id=context.correlation_id,
            )
            await mark_capability_committed(
                repository,
                creator_id=context.creator_id,
                universe_id=context.universe_id,
                mission_id=context.mission_id,
                opportunity_id=context.opportunity_id,
                amount=context.amount,
                currency=context.currency,
                external_reference=context.external_reference,
                correlation_id=context.correlation_id,
            )
            await mark_capability_settling(
                repository,
                creator_id=context.creator_id,
                universe_id=context.universe_id,
                mission_id=context.mission_id,
                opportunity_id=context.opportunity_id,
                amount=context.amount,
                currency=context.currency,
                external_reference=context.external_reference,
                correlation_id=context.correlation_id,
            )
            return context

    @staticmethod
    def _confirmed_pnl(result: CapabilityResult) -> Decimal:
        if not result.ok:
            return Decimal("0")
        raw = (result.data.get("economic") or {}).get("pnl") if isinstance(result.data, dict) else None
        return Decimal(str(raw)) if raw is not None else Decimal("0")

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
