from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import actor, correlation_id
from app.cognition.trinity import TrinityEngine
from app.config import settings
from app.core.domain import Actor
from app.db.session import AsyncSessionLocal, get_session
from app.inference.bootstrap import build_model_router, resolve_configured_model
from app.inference.contracts import InferenceError
from app.models.entities import Conversation
from app.observability.telemetry import traced
from app.repositories.domain import DomainRepository
from app.schemas.conversation import ConversationMessageResponse, MessageRequest, MessageResponse
from app.services.deus import DeusConversationService
from app.services.deus_context import DeusContextBuilder
from app.services.deus_turns import TurnConflict, TurnStore
from app.services.domain import NotFoundError

router = APIRouter()


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
@traced("deus.turn")
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

    model = resolve_configured_model(router_instance)
    trinity = TrinityEngine(
        router_instance,
        provider=settings.llm_provider,
        model=model,
        min_confidence=settings.trinity_min_confidence,
    ) if settings.trinity_enabled else None
    service = DeusConversationService(
        DomainRepository(session),
        router_instance,
        provider=settings.llm_provider,
        model=model,
        trinity=trinity,
        context_builder=DeusContextBuilder(AsyncSessionLocal) if settings.deus_context_retrieval_enabled else None,
        provider_timeout_seconds=settings.deus_chat_provider_timeout_seconds,
        total_timeout_seconds=settings.deus_chat_total_timeout_seconds,
    )
    turn = None
    store = TurnStore(AsyncSessionLocal)
    if body.request_id is not None:
        try:
            turn = await store.claim(a.id, str(entity_id), str(body.request_id), body.content)
        except TurnConflict as exc:
            raise HTTPException(409, str(exc), headers={'Retry-After':'2'}) from exc
        except LookupError as exc:
            raise HTTPException(404, 'Conversation not found') from exc
        if turn.response is not None:
            return MessageResponse(**turn.response)
    def response_for(result):
        return MessageResponse(message_id=result.creator_message_id,
            conversation_id=result.conversation_id, route='deus', response=result.response,
            inception=result.inception, system_state=None, correlation_id=cid)

    async def commit_guard(result):
        await store.finish_in_session(session, turn, response_for(result).model_dump(mode='json'), 'completed')

    try:
        if turn is not None:
            async with store.renewing(turn):
                result = await service.respond(a, str(entity_id), body.content, cid, commit_guard=commit_guard)
        else:
            result = await service.respond(a, str(entity_id), body.content, cid)
    except TurnConflict as exc:
        await session.rollback()
        raise HTTPException(409, 'Generation ownership expired; use a new request_id') from exc
    except asyncio.CancelledError:
        await session.rollback()
        if turn is not None:
            try:
                await asyncio.shield(store.finish(turn, None, 'interrupted'))
            except TurnConflict:
                pass
        raise
    except NotFoundError as exc:
        if turn is not None:
            await store.finish(turn, None, 'failed')
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InferenceError as exc:
        # Every provider in the chain failed. Say so plainly (503) instead of an opaque 500, and name
        # which provider and why in the log so the cause is found without guessing.
        await session.rollback()
        if turn is not None:
            await store.finish(turn, None, 'failed')
        logger.bind(component="deus", provider=exc.provider, code=exc.code).warning(
            "DEUS could not get an answer from any inference provider: {}", exc)
        raise HTTPException(status_code=503, detail="DEUS could not reach any inference provider right now") from exc

    except Exception:
        await session.rollback()
        if turn is not None:
            try:
                await store.finish(turn, None, 'failed')
            except TurnConflict:
                pass
        raise

    return response_for(result)
