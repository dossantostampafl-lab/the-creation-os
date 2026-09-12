from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.config import settings
from app.core.domain import Actor
from app.db.session import get_session
from app.inference.bootstrap import build_model_router
from app.models.entities import Conversation
from app.repositories.domain import DomainRepository
from app.schemas.auth import TokenPayload
from app.schemas.conversation import ConversationMessageResponse, MessageRequest, MessageResponse
from app.services.deus import DeusConversationService
from app.services.domain import NotFoundError

router = APIRouter()


def correlation_id(x_correlation_id: str | None = Header(None)) -> str:
    return str(uuid.uuid4()) if x_correlation_id is None else str(uuid.UUID(x_correlation_id))


def actor(token: TokenPayload = Depends(get_sovereign_creator)) -> Actor:
    return Actor(id=token.sub, role="creator")


@router.get("/conversations/{entity_id}/messages", response_model=list[ConversationMessageResponse])
async def list_messages(
    entity_id: uuid.UUID,
    a: Actor = Depends(actor),
    session: AsyncSession = Depends(get_session),
):
    repo = DomainRepository(session)
    conversation_id = str(entity_id)
    conversation = await repo.get(Conversation, conversation_id)
    owner_id = await repo.owner_id(Conversation, conversation_id) if conversation is not None else None
    if conversation is None or owner_id != a.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return [
        ConversationMessageResponse(**{name: getattr(item, name) for name in ConversationMessageResponse.model_fields})
        for item in await repo.list_messages(conversation_id, limit=100)
    ]


@router.post("/conversations/{entity_id}/deus", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def converse_with_deus(
    entity_id: uuid.UUID,
    body: MessageRequest,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        router_instance = build_model_router()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Inference provider is not configured") from exc

    service = DeusConversationService(
        DomainRepository(session),
        router_instance,
        provider=settings.llm_provider,
        model=settings.llm_model,
    )
    try:
        result = await service.respond(a, str(entity_id), body.content, cid)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return MessageResponse(
        message_id=result.creator_message_id,
        conversation_id=result.conversation_id,
        route="deus",
        response=result.response,
        inception=None,
        system_state=None,
        correlation_id=cid,
    )
