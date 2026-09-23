from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import actor, correlation_id
from app.auth.dependencies import get_sovereign_creator
from app.core.domain import Actor
from app.db.session import get_session
from app.repositories.domain import DomainRepository
from app.schemas.voice import VoiceSynthesisRequest
from app.services.voice import (
    VOICE_PROVIDER_UNAVAILABLE,
    VOICE_SYNTHESIS_DISABLED,
    VOICE_SYNTHESIS_EMPTY_TEXT,
    VOICE_SYNTHESIS_TEXT_TOO_LONG,
    VoiceSynthesisService,
)

router = APIRouter(tags=["voice"], dependencies=[Depends(get_sovereign_creator)])


def service(session: AsyncSession = Depends(get_session)) -> VoiceSynthesisService:
    return VoiceSynthesisService(DomainRepository(session))


@router.post("/voice/synthesize")
async def synthesize_voice(
    body: VoiceSynthesisRequest,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    voice_service: VoiceSynthesisService = Depends(service),
):
    try:
        audio, content_type = await voice_service.synthesize(a, body.text, cid)
    except VOICE_SYNTHESIS_DISABLED as exc:
        # Not configured on this installation; clients should stop asking and use a local voice.
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
    except (VOICE_SYNTHESIS_EMPTY_TEXT, VOICE_SYNTHESIS_TEXT_TOO_LONG) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except VOICE_PROVIDER_UNAVAILABLE as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return Response(content=audio, media_type=content_type)
