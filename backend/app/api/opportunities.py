from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.core.domain import Actor
from app.db.session import get_session
from app.models.opportunity import Opportunity, OpportunityObservation
from app.repositories.opportunities import OpportunityRepository
from app.schemas.auth import TokenPayload
from app.schemas.opportunities import (
    DiscoveryRunRequest,
    DiscoveryRunResponse,
    ObservationCreateRequest,
    ObservationResponse,
    OpportunityResponse,
    OpportunityReviewRequest,
)
from app.services.opportunities import OpportunityDiscoveryService

router = APIRouter(tags=["opportunities"], dependencies=[Depends(get_sovereign_creator)])


def correlation_id(x_correlation_id: str | None = Header(None)) -> str:
    return str(uuid.UUID(x_correlation_id)) if x_correlation_id else str(uuid.uuid4())


def actor(token: TokenPayload = Depends(get_sovereign_creator)) -> Actor:
    return Actor(id=token.sub, role="creator")


def service(session: AsyncSession = Depends(get_session)) -> OpportunityDiscoveryService:
    return OpportunityDiscoveryService(OpportunityRepository(session))


def observation_response(item: OpportunityObservation) -> ObservationResponse:
    return ObservationResponse(
        id=item.id,
        universe=item.universe,
        source=item.source,
        subject=item.subject,
        event_type=item.event_type,
        title=item.title,
        summary=item.summary,
        observed_at=item.observed_at,
        normalized_data=item.normalized_data,
        evidence=item.evidence,
        source_reliability=item.source_reliability,
        correlation_key=item.correlation_key,
        created_at=item.created_at,
    )


def opportunity_response(item: Opportunity) -> OpportunityResponse:
    return OpportunityResponse(
        id=item.id,
        title=item.title,
        universe=item.universe,
        category=item.category,
        status=item.status,
        summary=item.summary,
        explanation=item.explanation,
        confidence=item.confidence,
        impact=item.impact,
        urgency=item.urgency,
        risk=item.risk,
        priority_score=item.priority_score,
        recommended_action=item.recommended_action,
        evidence=item.evidence,
        risks=item.risks,
        scoring=item.scoring,
        detected_at=item.detected_at,
        expires_at=item.expires_at,
        reviewed_at=item.reviewed_at,
        reviewed_by=item.reviewed_by,
        rejection_reason=item.rejection_reason,
        inception_id=item.inception_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/observations", response_model=list[ObservationResponse])
async def list_observations(
    universe: str | None = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    items = await OpportunityRepository(session).observations(universe=universe, limit=limit, offset=offset)
    return [observation_response(item) for item in items]


@router.post("/observations", response_model=ObservationResponse, status_code=201)
async def ingest_observation(
    body: ObservationCreateRequest,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    s: OpportunityDiscoveryService = Depends(service),
):
    return observation_response(await s.ingest_observation(a, body.model_dump(), cid))


@router.get("/opportunities", response_model=list[OpportunityResponse])
async def list_opportunities(
    universe: str | None = None,
    status: str | None = None,
    min_priority: float | None = Query(None, ge=0, le=1),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    a: Actor = Depends(actor),
    s: OpportunityDiscoveryService = Depends(service),
):
    return [opportunity_response(item) for item in await s.list_opportunities(a, universe, status, min_priority, limit, offset)]


@router.get("/opportunities/ranking", response_model=list[OpportunityResponse])
async def ranking(
    universe: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    a: Actor = Depends(actor),
    s: OpportunityDiscoveryService = Depends(service),
):
    return [opportunity_response(item) for item in await s.ranking(a, universe, limit)]


@router.post("/opportunities/expire", response_model=list[OpportunityResponse])
async def expire_opportunities(a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: OpportunityDiscoveryService = Depends(service)):
    return [opportunity_response(item) for item in await s.expire(a, cid)]


@router.post("/opportunities/discovery/run", response_model=DiscoveryRunResponse)
async def run_discovery(
    body: DiscoveryRunRequest,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    s: OpportunityDiscoveryService = Depends(service),
):
    items = await s.run_discovery(a, [item.model_dump() for item in body.observations], cid)
    return DiscoveryRunResponse(opportunities=[opportunity_response(item) for item in items])


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityResponse)
async def get_opportunity(opportunity_id: uuid.UUID, a: Actor = Depends(actor), s: OpportunityDiscoveryService = Depends(service)):
    return opportunity_response(await s.get_opportunity(a, str(opportunity_id)))


@router.post("/opportunities/{opportunity_id}/approve", response_model=OpportunityResponse)
async def approve_opportunity(
    opportunity_id: uuid.UUID,
    body: OpportunityReviewRequest,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    s: OpportunityDiscoveryService = Depends(service),
):
    return opportunity_response(await s.approve(a, str(opportunity_id), body.reason, cid))


@router.post("/opportunities/{opportunity_id}/reject", response_model=OpportunityResponse)
async def reject_opportunity(
    opportunity_id: uuid.UUID,
    body: OpportunityReviewRequest,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    s: OpportunityDiscoveryService = Depends(service),
):
    return opportunity_response(await s.reject(a, str(opportunity_id), body.reason, cid))


@router.post("/opportunities/{opportunity_id}/convert-to-inception", response_model=OpportunityResponse)
async def convert_to_inception(
    opportunity_id: uuid.UUID,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    s: OpportunityDiscoveryService = Depends(service),
):
    return opportunity_response(await s.convert_to_inception(a, str(opportunity_id), cid))
