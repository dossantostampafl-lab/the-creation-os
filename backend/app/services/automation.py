from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.automation.contracts import ConnectorRequest
from app.automation.executor import AutomationExecutor, request_fingerprint
from app.automation.registry import ConnectorRegistry, default_registry
from app.core.domain import Actor, DomainError, require_creator
from app.models.automation import AutomationExecution
from app.repositories.automation import AutomationRepository
from app.repositories.capabilities import CapabilityRepository
from app.repositories.domain import sanitize
from app.services.capability_governance import CapabilityGovernanceService


class AutomationError(DomainError):
    pass


class AutomationIdempotencyConflict(AutomationError):
    pass


class AutomationService:
    def __init__(
        self,
        repository: AutomationRepository,
        registry: ConnectorRegistry | None = None,
        governance_service: CapabilityGovernanceService | None = None,
    ) -> None:
        self.repository = repository
        self.registry = registry or default_registry()
        self.governance_service = governance_service
        self.executor = AutomationExecutor(self.registry)

    async def execute(
        self,
        actor: Actor,
        *,
        connector_id: str,
        capability: str,
        payload: dict,
        timeout_seconds: float,
        idempotency_key: str,
        correlation_id: str,
    ) -> tuple[AutomationExecution, bool]:
        require_creator(actor, "execute automation connector")
        if timeout_seconds <= 0 or timeout_seconds > 30:
            raise AutomationError("Automation timeout must be between 0 and 30 seconds")
        authorization = await self._governance().authorize_execution(
            actor,
            connector_id=connector_id,
            connector_capability=capability,
            correlation_id=correlation_id,
        )
        request = ConnectorRequest(
            connector_id=connector_id,
            capability=capability,
            payload=payload,
            timeout_seconds=timeout_seconds,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )
        fingerprint = request_fingerprint(request)
        existing = await self.repository.execution(actor.id, connector_id, idempotency_key)
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise AutomationIdempotencyConflict("Idempotency key already used with a different automation request")
            await self.repository.commit()
            return existing, False

        document = await self.executor.execute(request)
        result = document.result
        try:
            item = await self.repository.add(
                AutomationExecution(
                    creator_id=actor.id,
                    connector_id=connector_id,
                    capability=capability,
                    idempotency_key=idempotency_key,
                    request_fingerprint=document.request_fingerprint,
                    request_payload=sanitize(payload),
                    status=result.status.value,
                    result_payload=sanitize(result.output),
                    error_code=result.error_code,
                    error_message=result.error_message,
                )
            )
            await self.repository.add_event(
                item.id,
                actor.id,
                actor.role,
                correlation_id,
                {
                    "execution_id": item.id,
                    "connector_id": connector_id,
                    "capability": capability,
                    "capability_id": authorization.capability.capability_id,
                    "capability_version": authorization.capability.version,
                    "capability_framework_version": authorization.framework_version,
                    "status": item.status,
                    "request_fingerprint": item.request_fingerprint,
                    "error_code": item.error_code,
                },
            )
            await self.repository.commit()
            return item, True
        except IntegrityError as exc:
            await self.repository.rollback()
            existing = await self.repository.execution(actor.id, connector_id, idempotency_key)
            if existing is not None:
                if existing.request_fingerprint != fingerprint:
                    raise AutomationIdempotencyConflict("Idempotency key already used with a different automation request") from exc
                return existing, False
            raise AutomationError("Automation execution could not be persisted atomically") from exc
        except Exception:
            await self.repository.rollback()
            raise

    def _governance(self) -> CapabilityGovernanceService:
        if self.governance_service is not None:
            return self.governance_service
        return CapabilityGovernanceService(CapabilityRepository(self.repository.session), connector_registry=self.registry)
