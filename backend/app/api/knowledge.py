from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import actor
from app.core.domain import Actor
from app.db.session import get_session
from app.knowledge.contracts import Candidate, Scope
from app.knowledge.service import KnowledgeConflict, KnowledgeService
from app.models.knowledge import ContextTrace, KnowledgeItem, KnowledgeProject, KnowledgeRelation

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

class WriteRequest(BaseModel):
    candidate: Candidate
    request_id: UUID
    expected_revision_id: UUID | None = None

class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2048)
    project_id: UUID | None = None

class ProjectRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)

class RelationRequest(BaseModel):
    from_id: UUID
    to_id: UUID
    kind: str = Field(pattern="^(belongs_to|derives_from|depends_on|supersedes|contradicts|related_to)$")

@router.post("/projects", status_code=201)
async def create_project(body: ProjectRequest, a: Actor = Depends(actor), session: AsyncSession = Depends(get_session)):
    project = KnowledgeProject(creator_id=a.id, title=body.title)
    session.add(project)
    await session.commit()
    return {"id": project.id, "title": project.title}

@router.post("/items", status_code=201)
async def create_item(body: WriteRequest, a: Actor = Depends(actor), session: AsyncSession = Depends(get_session)):
    try:
        result = await KnowledgeService(session).write(Scope(creator_id=a.id), body.candidate, str(body.request_id))
        await session.commit()
        return result
    except KnowledgeConflict as exc:
        await session.rollback()
        raise HTTPException(409, str(exc)) from exc

@router.post("/items/{item_id}/revisions", status_code=201)
async def revise_item(item_id: UUID, body: WriteRequest, a: Actor = Depends(actor), session: AsyncSession = Depends(get_session)):
    if body.expected_revision_id is None:
        raise HTTPException(422, "expected_revision_id is required")
    try:
        result = await KnowledgeService(session).write(Scope(creator_id=a.id), body.candidate, str(body.request_id), str(item_id), str(body.expected_revision_id))
        await session.commit()
        return result
    except KnowledgeConflict as exc:
        await session.rollback()
        raise HTTPException(409, str(exc)) from exc

@router.get("/items/{item_id}")
async def get_item(item_id: UUID, a: Actor = Depends(actor), session: AsyncSession = Depends(get_session)):
    row = await KnowledgeService(session).get(Scope(creator_id=a.id), str(item_id))
    if row is None:
        raise HTTPException(404, "Item not found")
    return {"id": row.item_id, "revision_id": row.id, "title": row.title, "content": row.content, "kind": row.kind, "status": row.lifecycle, "epistemic_state": row.epistemic_state}

@router.delete("/items/{item_id}")
async def revoke_item(item_id: UUID, expected_revision_id: UUID, a: Actor = Depends(actor), session: AsyncSession = Depends(get_session)):
    try:
        result = await KnowledgeService(session).revoke(Scope(creator_id=a.id), str(item_id), str(expected_revision_id))
        await session.commit()
        return result
    except KnowledgeConflict as exc:
        raise HTTPException(409, str(exc)) from exc

@router.post("/search")
async def search(body: SearchRequest, a: Actor = Depends(actor), session: AsyncSession = Depends(get_session)):
    return await KnowledgeService(session).search(Scope(creator_id=a.id, project_id=str(body.project_id) if body.project_id else None), body.query)

@router.post("/relations", status_code=201)
async def relate(body: RelationRequest, a: Actor = Depends(actor), session: AsyncSession = Depends(get_session)):
    for item_id in [body.from_id, body.to_id]:
        if await session.scalar(select(KnowledgeItem.id).where(KnowledgeItem.id == str(item_id), KnowledgeItem.creator_id == a.id, KnowledgeItem.active.is_(True))) is None:
            raise HTTPException(404, "Item not found")
    relation = KnowledgeRelation(creator_id=a.id, from_id=str(body.from_id), to_id=str(body.to_id), kind=body.kind)
    session.add(relation)
    await session.commit()
    return {"id": relation.id}

@router.get("/context-traces/{trace_id}")
async def trace(trace_id: UUID, a: Actor = Depends(actor), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    row = await session.scalar(select(ContextTrace).where(ContextTrace.id == str(trace_id), ContextTrace.creator_id == a.id))
    if row is None:
        raise HTTPException(404, "Trace not found")
    return row.data
