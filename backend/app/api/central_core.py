from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.db.session import get_session
from app.models.decision import MissionDecision
from app.models.policy import MissionDecisionReasoning
from app.repositories.decision import DecisionRepository
from app.repositories.policy import PolicyRepository
from app.schemas.auth import TokenPayload
from app.schemas.decision import MissionDecisionResponse
from app.schemas.policy import MissionDecisionReasoningResponse
from app.services.decision import DecisionService
from app.services.policy import PolicyService

router = APIRouter(tags=["central-core"], dependencies=[Depends(get_sovereign_creator)])


def correlation_id(x_correlation_id: str | None = Header(None)) -> str:
    return str(uuid.UUID(x_correlation_id)) if x_correlation_id else str(uuid.uuid4())


def service(session: AsyncSession = Depends(get_session)) -> DecisionService:
    return DecisionService(DecisionRepository(session))


def reasoning_service(session: AsyncSession = Depends(get_session)) -> PolicyService:
    return PolicyService(PolicyRepository(session))


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


def reasoning_response(item: MissionDecisionReasoning) -> MissionDecisionReasoningResponse:
    return MissionDecisionReasoningResponse(
        id=item.id,
        decision_id=item.decision_id,
        policy_version=item.policy_version,
        evaluation_timestamp=item.evaluation_timestamp,
        rules_applied=item.rules_applied,
        consistency_summary=item.consistency_summary,
        completeness_summary=item.completeness_summary,
        explanation_payload=item.explanation_payload,
        fingerprint=item.fingerprint,
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
    actor: TokenPayload = Depends(get_sovereign_creator),
    cid: str = Depends(correlation_id),
    decision_service: DecisionService = Depends(service),
):
    item, created = await decision_service.decide(
        str(mission_id), correlation_id=cid, actor_id=actor.sub, actor_role="creator"
    )
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


@router.post(
    "/central-core/missions/{mission_id}/evaluate",
    response_model=MissionDecisionReasoningResponse,
    status_code=status.HTTP_201_CREATED,
)
async def evaluate_mission_decision(
    mission_id: uuid.UUID,
    response: Response,
    policy_service: PolicyService = Depends(reasoning_service),
):
    item, created = await policy_service.evaluate(str(mission_id))
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return reasoning_response(item)


@router.get(
    "/central-core/missions/{mission_id}/reasoning",
    response_model=MissionDecisionReasoningResponse,
)
async def get_mission_reasoning(
    mission_id: uuid.UUID,
    policy_service: PolicyService = Depends(reasoning_service),
):
    return reasoning_response(await policy_service.get(str(mission_id)))
