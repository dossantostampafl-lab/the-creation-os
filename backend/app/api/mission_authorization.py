from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.core.domain import Actor
from app.db.session import get_session
from app.models.mission_authorization import MissionAuthorization
from app.repositories.mission_authorization import MissionAuthorizationRepository
from app.schemas.auth import TokenPayload
from app.schemas.mission_authorization import (
    MissionAuthorizationCheckRequest,
    MissionAuthorizationRequest,
    MissionAuthorizationResponse,
)
from app.services.mission_authorization import MissionActionContext, MissionAuthorizationService

router = APIRouter(prefix="/missions/{mission_id}/authorization", tags=["mission-authorization"], dependencies=[Depends(get_sovereign_creator)])


def correlation_id(x_correlation_id: str | None = Header(None)) -> str:
    return str(uuid.UUID(x_correlation_id)) if x_correlation_id else str(uuid.uuid4())


def actor(token: TokenPayload = Depends(get_sovereign_creator)) -> Actor:
    return Actor(id=token.sub, role="creator")


def service(session: AsyncSession = Depends(get_session)) -> MissionAuthorizationService:
    return MissionAuthorizationService(MissionAuthorizationRepository(session))


def response(item: MissionAuthorization) -> MissionAuthorizationResponse:
    return MissionAuthorizationResponse(
        id=item.id,
        mission_id=item.mission_id,
        project_id=item.project_id,
        creator_id=item.creator_id,
        status=item.status,
        scope_json=item.scope_json,
        allowed_capabilities_json=list(item.allowed_capabilities_json or []),
        allowed_resources_json=list(item.allowed_resources_json or []),
        restrictions_json=item.restrictions_json,
        approved_at=item.approved_at,
        suspended_at=item.suspended_at,
        revoked_at=item.revoked_at,
        completed_at=item.completed_at,
        expires_at=item.expires_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
        metadata_json=item.metadata_json,
    )


@router.get("", response_model=MissionAuthorizationResponse | None)
async def get_authorization(mission_id: uuid.UUID, a: Actor = Depends(actor), s: MissionAuthorizationService = Depends(service)):
    item = await s.get(a, str(mission_id))
    return response(item) if item else None


@router.post("/request", response_model=MissionAuthorizationResponse, status_code=status.HTTP_201_CREATED)
async def request_authorization(
    mission_id: uuid.UUID,
    body: MissionAuthorizationRequest,
    http_response: Response,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    s: MissionAuthorizationService = Depends(service),
):
    item = await s.request_authorization(
        a,
        str(mission_id),
        project_id=body.project_id,
        scope=body.scope,
        allowed_capabilities=body.allowed_capabilities,
        allowed_resources=body.allowed_resources,
        restrictions=body.restrictions,
        expires_at=body.expires_at,
        metadata=body.metadata,
        correlation_id=cid,
    )
    http_response.status_code = status.HTTP_201_CREATED if item.status == "pending" else status.HTTP_200_OK
    return response(item)


@router.post("/approve", response_model=MissionAuthorizationResponse)
async def approve_authorization(mission_id: uuid.UUID, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: MissionAuthorizationService = Depends(service)):
    return response(await s.approve(a, str(mission_id), cid))


@router.post("/suspend", response_model=MissionAuthorizationResponse)
async def suspend_authorization(mission_id: uuid.UUID, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: MissionAuthorizationService = Depends(service)):
    return response(await s.suspend(a, str(mission_id), cid))


@router.post("/revoke", response_model=MissionAuthorizationResponse)
async def revoke_authorization(mission_id: uuid.UUID, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: MissionAuthorizationService = Depends(service)):
    return response(await s.revoke(a, str(mission_id), cid))


@router.post("/complete", response_model=MissionAuthorizationResponse)
async def complete_authorization(mission_id: uuid.UUID, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: MissionAuthorizationService = Depends(service)):
    return response(await s.complete(a, str(mission_id), cid))


@router.post("/check", response_model=MissionAuthorizationResponse)
async def check_authorization(
    mission_id: uuid.UUID,
    body: MissionAuthorizationCheckRequest,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    s: MissionAuthorizationService = Depends(service),
):
    item = await s.check_action(
        a,
        MissionActionContext(
            mission_id=str(mission_id),
            project_id=body.project_id,
            action=body.action,
            capability_id=body.capability_id,
            resource=body.resource,
            reason=body.reason,
        ),
        cid,
    )
    return response(item)
