from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.core.domain import Actor
from app.db.session import get_session
from app.repositories.creator_recall import CreatorRecallRepository
from app.schemas.auth import TokenPayload
from app.schemas.memory import MemoryCreateRequest, MemoryResponse, MemorySearchResponse, MemoryTypeLiteral
from app.services.creator_recall import CreatorRecallService, RememberedMemory

# NOTE (Lote: fechar gap de POST /memory, 2026-08-01): this route now
# writes/reads conversation_memory via CreatorRecallService, so memories
# created here ARE visible to GOD's memory recall (see
# app/repositories/god.py::conversation_memory_candidates) — closes the
# gap left open by the previous convergence lote. MemoryService /
# MemoryRepository / CreatorMemory remain deprecated and are no longer
# called by this route.
router = APIRouter(tags=["memory"], dependencies=[Depends(get_sovereign_creator)])


def correlation_id(x_correlation_id: str | None = Header(None)) -> str:
    if x_correlation_id is None:
        return str(uuid.uuid4())
    return str(uuid.UUID(x_correlation_id))


def actor(token: TokenPayload = Depends(get_sovereign_creator)) -> Actor:
    return Actor(id=token.sub, role="creator")


def service(session: AsyncSession = Depends(get_session)) -> CreatorRecallService:
    return CreatorRecallService(CreatorRecallRepository(session))


def memory_response(item: RememberedMemory) -> MemoryResponse:
    return MemoryResponse(
        id=item.id,
        creator_id=item.creator_id,
        memory_type=item.memory_type,
        source=item.source,
        content=item.content,
        importance=item.importance,
        metadata=item.metadata_json,
        memory_fingerprint=item.memory_fingerprint,
        created_at=item.created_at,
    )


@router.post("/memory", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def remember(
    request: MemoryCreateRequest,
    response: Response,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    memory_service: CreatorRecallService = Depends(service),
):
    item, created = await memory_service.remember(
        a,
        memory_type=request.memory_type,
        content=request.content,
        source=request.source,
        importance=request.importance,
        metadata=request.metadata,
        correlation_id=cid,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return memory_response(item)


@router.get("/memory/search", response_model=MemorySearchResponse)
async def search_memory(
    q: str | None = Query(None, min_length=1),
    memory_type: MemoryTypeLiteral | None = None,
    min_importance: int = Query(1, ge=1, le=10),
    limit: int = Query(20, ge=1, le=100),
    a: Actor = Depends(actor),
    memory_service: CreatorRecallService = Depends(service),
):
    items = await memory_service.search(a, query=q, memory_type=memory_type, min_importance=min_importance, limit=limit)
    return MemorySearchResponse(items=[memory_response(item) for item in items])
