from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.core.domain import Actor
from app.db.session import get_session
from app.models.sophia import SophiaUnderstanding
from app.repositories.sophia import SophiaRepository
from app.schemas.auth import TokenPayload
from app.schemas.sophia import SophiaUnderstandingResponse
from app.services.sophia import SophiaService

router = APIRouter(tags=["sophia"], dependencies=[Depends(get_sovereign_creator)])


def correlation_id(x_correlation_id: str | None = Header(None)) -> str:
    if x_correlation_id is None:
        return str(uuid.uuid4())
    return str(uuid.UUID(x_correlation_id))


def actor(token: TokenPayload = Depends(get_sovereign_creator)) -> Actor:
    return Actor(id=token.sub, role="creator")


def service(session: AsyncSession = Depends(get_session)) -> SophiaService:
    return SophiaService(SophiaRepository(session))


def sophia_response(item: SophiaUnderstanding) -> SophiaUnderstandingResponse:
    return SophiaUnderstandingResponse(
        id=item.id,
        god_interaction_id=item.god_interaction_id,
        conversation_id=item.conversation_id,
        understanding_type=item.understanding_type,
        understanding_payload=item.understanding_payload,
        source_fingerprint=item.source_fingerprint,
        understanding_fingerprint=item.understanding_fingerprint,
        created_at=item.created_at,
        understood_at=item.understood_at,
    )


@router.post(
    "/sophia/god-interactions/{interaction_id}/understand",
    response_model=SophiaUnderstandingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def understand_god_interaction(
    interaction_id: uuid.UUID,
    response: Response,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    sophia_service: SophiaService = Depends(service),
):
    item, created = await sophia_service.understand(a, str(interaction_id), cid)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return sophia_response(item)


@router.get(
    "/sophia/god-interactions/{interaction_id}/understanding",
    response_model=SophiaUnderstandingResponse,
)
async def get_god_interaction_understanding(
    interaction_id: uuid.UUID,
    a: Actor = Depends(actor),
    sophia_service: SophiaService = Depends(service),
):
    return sophia_response(await sophia_service.get(a, str(interaction_id)))
