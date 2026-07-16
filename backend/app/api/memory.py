from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.core.domain import Actor
from app.db.session import get_session
from app.models.memory import CreatorMemory
from app.repositories.memory import MemoryRepository
from app.schemas.auth import TokenPayload
from app.schemas.memory import MemoryCreateRequest, MemoryResponse, MemorySearchResponse, MemoryTypeLiteral
from app.services.memory import MemoryService

router = APIRouter(tags=["memory"], dependencies=[Depends(get_sovereign_creator)])


def correlation_id(x_correlation_id: str | None = Header(None)) -> str:
    if x_correlation_id is None:
        return str(uuid.uuid4())
    return str(uuid.UUID(x_correlation_id))


def actor(token: TokenPayload = Depends(get_sovereign_creator)) -> Actor:
    return Actor(id=token.sub, role="creator")


def service(session: AsyncSession = Depends(get_session)) -> MemoryService:
    return MemoryService(MemoryRepository(session))


def memory_response(item: CreatorMemory) -> MemoryResponse:
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
    memory_service: MemoryService = Depends(service),
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
    limit: int = Query(20, ge=1, le=100),
    a: Actor = Depends(actor),
    memory_service: MemoryService = Depends(service),
):
    items = await memory_service.search(a, query=q, memory_type=memory_type, limit=limit)
    return MemorySearchResponse(items=[memory_response(item) for item in items])
