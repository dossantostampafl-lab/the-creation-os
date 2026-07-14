from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.db.session import get_session
from app.models.decision import MissionDecision
from app.repositories.decision import DecisionRepository
from app.schemas.decision import MissionDecisionResponse
from app.services.decision import DecisionService

router = APIRouter(tags=["central-core"], dependencies=[Depends(get_sovereign_creator)])


def service(session: AsyncSession = Depends(get_session)) -> DecisionService:
    return DecisionService(DecisionRepository(session))


def decision_response(item: MissionDecision) -> MissionDecisionResponse:
    return MissionDecisionResponse(
        id=item.id,
        mission_id=item.mission_id,
        consolidation_id=item.consolidation_id,
        decision=item.decision,
        justification=item.justification_json,
        consolidation_fingerprint=item.consolidation_fingerprint,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post(
    "/central-core/missions/{mission_id}/decide",
    response_model=MissionDecisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def decide_mission(
    mission_id: uuid.UUID,
    response: Response,
    decision_service: DecisionService = Depends(service),
):
    item, created = await decision_service.decide(str(mission_id))
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return decision_response(item)


@router.get(
    "/central-core/missions/{mission_id}/decision",
    response_model=MissionDecisionResponse,
)
async def get_mission_decision(
    mission_id: uuid.UUID,
    decision_service: DecisionService = Depends(service),
):
    return decision_response(await decision_service.get(str(mission_id)))
