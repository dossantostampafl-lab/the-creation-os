from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.core.domain import Actor
from app.db.session import get_session
from app.models.rockmam import RockmamPossibilityAssessment
from app.repositories.rockmam import RockmamRepository
from app.schemas.auth import TokenPayload
from app.schemas.rockmam import RockmamAssessmentResponse
from app.services.rockmam import RockmamService

router = APIRouter(tags=["rockmam"], dependencies=[Depends(get_sovereign_creator)])


def correlation_id(x_correlation_id: str | None = Header(None)) -> str:
    if x_correlation_id is None:
        return str(uuid.uuid4())
    return str(uuid.UUID(x_correlation_id))


def actor(token: TokenPayload = Depends(get_sovereign_creator)) -> Actor:
    return Actor(id=token.sub, role="creator")


def service(session: AsyncSession = Depends(get_session)) -> RockmamService:
    return RockmamService(RockmamRepository(session))


def rockmam_response(item: RockmamPossibilityAssessment) -> RockmamAssessmentResponse:
    return RockmamAssessmentResponse(
        id=item.id,
        sophia_understanding_id=item.sophia_understanding_id,
        conversation_id=item.conversation_id,
        assessment_result=item.assessment_result,
        assessment_payload=item.assessment_payload,
        source_fingerprint=item.source_fingerprint,
        assessment_fingerprint=item.assessment_fingerprint,
        created_at=item.created_at,
        assessed_at=item.assessed_at,
    )


@router.post(
    "/rockmam/sophia-understandings/{understanding_id}/assess",
    response_model=RockmamAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assess_sophia_understanding(
    understanding_id: uuid.UUID,
    response: Response,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    rockmam_service: RockmamService = Depends(service),
):
    item, created = await rockmam_service.assess(a, str(understanding_id), cid)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return rockmam_response(item)


@router.get(
    "/rockmam/sophia-understandings/{understanding_id}/assessment",
    response_model=RockmamAssessmentResponse,
)
async def get_sophia_understanding_assessment(
    understanding_id: uuid.UUID,
    a: Actor = Depends(actor),
    rockmam_service: RockmamService = Depends(service),
):
    return rockmam_response(await rockmam_service.get(a, str(understanding_id)))
