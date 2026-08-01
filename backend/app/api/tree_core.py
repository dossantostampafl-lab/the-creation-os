from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.db.session import get_session
from app.models.consolidation import MissionConsolidation
from app.models.entities import Agent, Capability
from app.repositories.consolidation import ConsolidationRepository
from app.repositories.tree_core import TreeCoreRepository
from app.schemas.auth import TokenPayload
from app.schemas.consolidation import MissionConsolidationResponse
from app.schemas.tree_core import (
    AgentCapabilityRequest,
    AgentCreateRequest,
    AgentResponse,
    AgentUpdateRequest,
    CapabilityCreateRequest,
    CapabilityResponse,
    TreeCoreMatchRequest,
    TreeCoreMatchResponse,
)
from app.services.consolidation import ConsolidationService
from app.services.tree_core import TreeCoreService

router = APIRouter(tags=["tree-core"], dependencies=[Depends(get_sovereign_creator)])


def correlation_id(x_correlation_id: str | None = Header(None)) -> str:
    return str(uuid.UUID(x_correlation_id)) if x_correlation_id else str(uuid.uuid4())


def service(session: AsyncSession = Depends(get_session)) -> TreeCoreService:
    return TreeCoreService(TreeCoreRepository(session))


def consolidation_service(session: AsyncSession = Depends(get_session)) -> ConsolidationService:
    return ConsolidationService(ConsolidationRepository(session))


def capability_response(item: Capability) -> CapabilityResponse:
    return CapabilityResponse(id=item.id, name=item.name, description=item.description)


def agent_response(item: Agent) -> AgentResponse:
    return AgentResponse(
        id=item.id,
        name=item.name,
        description=item.description,
        universe=item.universe_name,
        capabilities=[capability_response(capability) for capability in item.capabilities],
        priority=item.priority,
        status=item.status,
        version=item.version,
        heartbeat_at=item.heartbeat_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
        enabled=item.enabled,
    )


def consolidation_response(item: MissionConsolidation) -> MissionConsolidationResponse:
    return MissionConsolidationResponse(
        id=item.id,
        mission_id=item.mission_id,
        status=item.status,
        payload=item.payload_json,
        inconsistencies=item.inconsistencies_json,
        completeness=item.completeness_json,
        fingerprint=item.fingerprint,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/agents", response_model=list[AgentResponse])
async def list_agents(s: TreeCoreService = Depends(service)):
    return [agent_response(agent) for agent in await s.list_agents()]


@router.post("/agents", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def register_agent(body: AgentCreateRequest, s: TreeCoreService = Depends(service)):
    return agent_response(await s.register_agent(body.name, body.description, body.universe, body.priority, True))


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: uuid.UUID, s: TreeCoreService = Depends(service)):
    return agent_response(await s.get_agent(str(agent_id)))


@router.patch("/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: uuid.UUID, body: AgentUpdateRequest, s: TreeCoreService = Depends(service)):
    return agent_response(await s.update_agent(str(agent_id), **body.model_dump(exclude_unset=True)))


@router.post("/agents/{agent_id}/heartbeat", response_model=AgentResponse)
async def heartbeat(agent_id: uuid.UUID, s: TreeCoreService = Depends(service)):
    return agent_response(await s.heartbeat(str(agent_id)))


@router.post("/agents/{agent_id}/enable", response_model=AgentResponse)
async def enable_agent(agent_id: uuid.UUID, s: TreeCoreService = Depends(service)):
    return agent_response(await s.enable(str(agent_id)))


@router.post("/agents/{agent_id}/disable", response_model=AgentResponse)
async def disable_agent(agent_id: uuid.UUID, s: TreeCoreService = Depends(service)):
    return agent_response(await s.disable(str(agent_id)))


@router.get("/capabilities", response_model=list[CapabilityResponse])
async def list_capabilities(s: TreeCoreService = Depends(service)):
    return [capability_response(capability) for capability in await s.list_capabilities()]


@router.post("/capabilities", response_model=CapabilityResponse, status_code=status.HTTP_201_CREATED)
async def create_capability(body: CapabilityCreateRequest, s: TreeCoreService = Depends(service)):
    return capability_response(await s.create_capability(body.name, body.description))


@router.post("/agents/{agent_id}/capabilities", response_model=AgentResponse)
async def add_capability(agent_id: uuid.UUID, body: AgentCapabilityRequest, s: TreeCoreService = Depends(service)):
    return agent_response(await s.add_capability(str(agent_id), str(body.capability_id)))


@router.delete("/agents/{agent_id}/capabilities/{capability_id}", response_model=AgentResponse)
async def remove_capability(agent_id: uuid.UUID, capability_id: uuid.UUID, s: TreeCoreService = Depends(service)):
    return agent_response(await s.remove_capability(str(agent_id), str(capability_id)))


@router.post("/tree-core/match", response_model=TreeCoreMatchResponse)
async def match_agents(body: TreeCoreMatchRequest, s: TreeCoreService = Depends(service)):
    mission, agents = await s.match(str(body.mission_id), body.required_capabilities)
    return TreeCoreMatchResponse(mission_id=mission.id, agents=[agent_response(agent) for agent in agents])


@router.post(
    "/tree-core/missions/{mission_id}/consolidate",
    response_model=MissionConsolidationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def consolidate_mission(
    mission_id: uuid.UUID,
    response: Response,
    response_actor: TokenPayload = Depends(get_sovereign_creator),
    cid: str = Depends(correlation_id),
    s: ConsolidationService = Depends(consolidation_service),
):
    item, created = await s.consolidate(
        str(mission_id), correlation_id=cid, actor_id=response_actor.sub, actor_role="creator"
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return consolidation_response(item)


@router.get(
    "/tree-core/missions/{mission_id}/consolidation",
    response_model=MissionConsolidationResponse,
)
async def get_mission_consolidation(
    mission_id: uuid.UUID,
    s: ConsolidationService = Depends(consolidation_service),
):
    return consolidation_response(await s.get(str(mission_id)))
