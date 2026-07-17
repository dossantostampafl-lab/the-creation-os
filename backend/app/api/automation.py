from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.automation.registry import default_registry
from app.core.domain import Actor
from app.db.session import get_session
from app.models.automation import AutomationExecution
from app.models.capability_registry import RegisteredCapability
from app.repositories.automation import AutomationRepository
from app.repositories.capabilities import CapabilityRepository
from app.schemas.auth import TokenPayload
from app.schemas.automation import (
    AutomationCapabilityResponse,
    AutomationExecuteRequest,
    AutomationExecutionResponse,
    CapabilityFrameworkResponse,
)
from app.services.automation import AutomationService
from app.services.capabilities import CapabilityPersistenceService
from app.services.mission_authorization import MissionActionContext

router = APIRouter(tags=["automation"], dependencies=[Depends(get_sovereign_creator)])


def correlation_id(x_correlation_id: str | None = Header(None)) -> str:
    if x_correlation_id is None:
        return str(uuid.uuid4())
    return str(uuid.UUID(x_correlation_id))


def actor(token: TokenPayload = Depends(get_sovereign_creator)) -> Actor:
    return Actor(id=token.sub, role="creator")


def service(session: AsyncSession = Depends(get_session)) -> AutomationService:
    return AutomationService(AutomationRepository(session))


def capability_service(session: AsyncSession = Depends(get_session)) -> CapabilityPersistenceService:
    return CapabilityPersistenceService(CapabilityRepository(session))


def execution_response(item: AutomationExecution) -> AutomationExecutionResponse:
    return AutomationExecutionResponse(
        id=item.id,
        creator_id=item.creator_id,
        connector_id=item.connector_id,
        capability=item.capability,
        idempotency_key=item.idempotency_key,
        request_fingerprint=item.request_fingerprint,
        status=item.status,
        result_payload=item.result_payload,
        error_code=item.error_code,
        error_message=item.error_message,
        created_at=item.created_at,
        completed_at=item.completed_at,
    )


def persisted_capability_response(item: RegisteredCapability) -> CapabilityFrameworkResponse:
    return CapabilityFrameworkResponse(
        id=item.id,
        capability_id=item.capability_id,
        name=item.name,
        description=item.description,
        version=item.version,
        connector_id=item.connector_id,
        connector_capability=item.connector_capability,
        enabled=item.enabled,
        permissions=list(item.permissions_json),
        dependencies=list(item.dependencies_json),
        metadata=dict(item.metadata_json),
        mandatory=item.mandatory,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/automation/connectors", response_model=list[AutomationCapabilityResponse])
async def list_connectors():
    registry = default_registry()
    return [
        AutomationCapabilityResponse(
            connector_id=connector_id,
            capabilities=[
                {
                    "name": capability.name,
                    "description": capability.description,
                    "input_schema": capability.input_schema,
                }
                for capability in capabilities
            ],
        )
        for connector_id, capabilities in registry.list_capabilities().items()
    ]


@router.get("/automation/capabilities", response_model=list[CapabilityFrameworkResponse])
async def list_automation_capabilities(
    a: Actor = Depends(actor),
    capabilities: CapabilityPersistenceService = Depends(capability_service),
):
    return [persisted_capability_response(item) for item in await capabilities.list(a)]


@router.post("/automation/capabilities/{capability_id}/enable", response_model=CapabilityFrameworkResponse)
async def enable_automation_capability(
    capability_id: str,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    capabilities: CapabilityPersistenceService = Depends(capability_service),
):
    return persisted_capability_response(await capabilities.enable(a, capability_id, cid))


@router.post("/automation/capabilities/{capability_id}/disable", response_model=CapabilityFrameworkResponse)
async def disable_automation_capability(
    capability_id: str,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    capabilities: CapabilityPersistenceService = Depends(capability_service),
):
    return persisted_capability_response(await capabilities.disable(a, capability_id, cid))


@router.post("/automation/execute", response_model=AutomationExecutionResponse, status_code=status.HTTP_201_CREATED)
async def execute_automation(
    body: AutomationExecuteRequest,
    response: Response,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    automation_service: AutomationService = Depends(service),
):
    item, created = await automation_service.execute(
        a,
        connector_id=body.connector_id,
        capability=body.capability,
        payload=body.payload,
        timeout_seconds=body.timeout_seconds,
        idempotency_key=body.idempotency_key,
        correlation_id=cid,
        mission_context=MissionActionContext(
            mission_id=body.mission_id,
            project_id=body.project_id or "",
            action=body.action or "",
            capability_id="",
            resource=body.resource,
            reason=body.reason,
        )
        if body.mission_id
        else None,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return execution_response(item)
