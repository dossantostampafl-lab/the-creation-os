from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.automation.registry import default_registry
from app.core.domain import Actor
from app.db.session import get_session
from app.models.automation import AutomationExecution
from app.repositories.automation import AutomationRepository
from app.schemas.auth import TokenPayload
from app.schemas.automation import AutomationCapabilityResponse, AutomationExecuteRequest, AutomationExecutionResponse
from app.services.automation import AutomationService

router = APIRouter(tags=["automation"], dependencies=[Depends(get_sovereign_creator)])


def correlation_id(x_correlation_id: str | None = Header(None)) -> str:
    if x_correlation_id is None:
        return str(uuid.uuid4())
    return str(uuid.UUID(x_correlation_id))


def actor(token: TokenPayload = Depends(get_sovereign_creator)) -> Actor:
    return Actor(id=token.sub, role="creator")


def service(session: AsyncSession = Depends(get_session)) -> AutomationService:
    return AutomationService(AutomationRepository(session))


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
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return execution_response(item)
