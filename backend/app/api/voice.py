from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.core.domain import Actor
from app.db.session import get_session
from app.repositories.domain import DomainRepository
from app.schemas.auth import TokenPayload
from app.schemas.voice import VoiceSynthesisRequest
from app.services.voice import VoiceSynthesisService

router = APIRouter(tags=["voice"], dependencies=[Depends(get_sovereign_creator)])


def correlation_id(x_correlation_id: str | None = Header(None)) -> str:
    if x_correlation_id is None:
        return str(uuid.uuid4())
    return str(uuid.UUID(x_correlation_id))


def actor(token: TokenPayload = Depends(get_sovereign_creator)) -> Actor:
    return Actor(id=token.sub, role="creator")


def service(session: AsyncSession = Depends(get_session)) -> VoiceSynthesisService:
    return VoiceSynthesisService(DomainRepository(session))


@router.post("/voice/synthesize")
async def synthesize_voice(
    body: VoiceSynthesisRequest,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    voice_service: VoiceSynthesisService = Depends(service),
):
    audio, content_type = await voice_service.synthesize(a, body.text, cid)
    return Response(content=audio, media_type=content_type)
