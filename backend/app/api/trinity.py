from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.core.domain import Actor
from app.db.session import get_session
from app.repositories.trinity import TrinityRepository
from app.schemas.auth import TokenPayload
from app.schemas.trinity import TrinityOrchestrationResponse
from app.services.trinity import TrinityOrchestrationService, TrinityResult

router = APIRouter(tags=["trinity"], dependencies=[Depends(get_sovereign_creator)])


def correlation_id(x_correlation_id: str | None = Header(None)) -> str:
    if x_correlation_id is None:
        return str(uuid.uuid4())
    return str(uuid.UUID(x_correlation_id))


def actor(token: TokenPayload = Depends(get_sovereign_creator)) -> Actor:
    return Actor(id=token.sub, role="creator")


def service(session: AsyncSession = Depends(get_session)) -> TrinityOrchestrationService:
    return TrinityOrchestrationService(TrinityRepository(session))


def trinity_response(god_interaction_id: str, interaction_type: str, result: TrinityResult) -> TrinityOrchestrationResponse:
    return TrinityOrchestrationResponse(
        god_interaction_id=god_interaction_id,
        conversation_id=result.understanding.conversation_id,
        interaction_type=interaction_type,
        sophia_understanding_id=result.understanding.id,
        rockmam_assessment_id=result.assessment.id,
        assessment_result=result.assessment.assessment_result,
        understanding_created=result.understanding_created,
        assessment_created=result.assessment_created,
        god_consolidated_result={
            "source": "TRINITY",
            "received_by": "DEUS",
            "creator_approval_required": result.assessment.assessment_result == "REQUIRES_CREATOR",
            "creates_inception": False,
            "creates_mission": False,
            "assessment_result": result.assessment.assessment_result,
            "assessment_fingerprint": result.assessment.assessment_fingerprint,
        },
    )


@router.post(
    "/trinity/god-interactions/{interaction_id}/orchestrate",
    response_model=TrinityOrchestrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def orchestrate_trinity(
    interaction_id: uuid.UUID,
    response: Response,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    trinity_service: TrinityOrchestrationService = Depends(service),
):
    result = await trinity_service.orchestrate(a, str(interaction_id), cid)
    response.status_code = status.HTTP_201_CREATED if result.understanding_created or result.assessment_created else status.HTTP_200_OK
    return trinity_response(str(interaction_id), "POTENTIAL", result)
