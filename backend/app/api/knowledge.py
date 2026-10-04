from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import actor
from app.config import settings
from app.core.domain import Actor
from app.db.session import get_session
from app.diagnostics.context import current_diagnostics
from app.diagnostics.heartbeat import ServiceHeartbeat
from app.diagnostics.worker import collect as collect_live_diagnostics
from app.knowledge.contracts import Candidate, Scope
from app.knowledge.service import KnowledgeConflict, KnowledgeService
from app.models.entities import Conversation, ConversationMemory
from app.models.knowledge import ContextTrace, KnowledgeItem, KnowledgeProject, KnowledgeRelation
from app.repositories.domain import DomainRepository

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
    import uuid
    relation_id = str(uuid.uuid4())
    await session.execute(insert(KnowledgeRelation).values(id=relation_id, creator_id=a.id,
        from_id=relation.from_id, to_id=relation.to_id, kind=relation.kind).on_conflict_do_nothing(
            index_elements=['from_id', 'to_id', 'kind']))
    found_relation_id = await session.scalar(select(KnowledgeRelation.id).where(
        KnowledgeRelation.creator_id==a.id, KnowledgeRelation.from_id==relation.from_id,
        KnowledgeRelation.to_id==relation.to_id, KnowledgeRelation.kind==relation.kind))
    await session.commit()
    return {'id':found_relation_id}

@router.get("/context-traces/{trace_id}")
async def trace(trace_id: UUID, a: Actor = Depends(actor), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    row = await session.scalar(select(ContextTrace).where(ContextTrace.id == str(trace_id), ContextTrace.creator_id == a.id))
    if row is None:
        raise HTTPException(404, "Trace not found")
    return row.data


@router.get('/projects')
async def list_projects(a: Actor = Depends(actor), session: AsyncSession = Depends(get_session)):
    return [{'id':p.id, 'title':p.title} for p in await session.scalars(
        select(KnowledgeProject).where(KnowledgeProject.creator_id==a.id).order_by(KnowledgeProject.title).limit(100))]


class FocusRequest(BaseModel):
    project_id: UUID | None = None


@router.put('/conversations/{conversation_id}/focus')
async def set_focus(conversation_id: UUID, body: FocusRequest, a: Actor = Depends(actor), session: AsyncSession = Depends(get_session)):
    await session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'), {'key':'focus:'+str(conversation_id)})
    if not await session.scalar(select(Conversation.id).where(Conversation.id==str(conversation_id), Conversation.creator_id==a.id)):
        raise HTTPException(404, 'Conversation not found')
    if body.project_id and not await session.scalar(select(KnowledgeProject.id).where(KnowledgeProject.id==str(body.project_id), KnowledgeProject.creator_id==a.id)):
        raise HTTPException(404, 'Project not found')
    await DomainRepository(session).upsert_memory('conversation', str(conversation_id), 'deus_project_focus', {'project_id':str(body.project_id) if body.project_id else None})
    await session.commit()
    return {'project_id':str(body.project_id) if body.project_id else None}


@router.get('/conversations/{conversation_id}/focus')
async def get_focus(conversation_id: UUID, a: Actor = Depends(actor), session: AsyncSession = Depends(get_session)):
    if not await session.scalar(select(Conversation.id).where(Conversation.id==str(conversation_id), Conversation.creator_id==a.id)):
        raise HTTPException(404, 'Conversation not found')
    row = await session.scalar(select(ConversationMemory).where(ConversationMemory.conversation_id==str(conversation_id), ConversationMemory.key=='deus_project_focus'))
    return row.value_json if row else {'project_id':None}


@router.get('/diagnostics/current')
async def diagnostics(a: Actor = Depends(actor), session: AsyncSession = Depends(get_session)):
    observations = await current_diagnostics(session, a.id)
    now = datetime.now(timezone.utc)
    observer_fresh = await session.scalar(
        select(ServiceHeartbeat.service).where(
            ServiceHeartbeat.service == 'diagnostics-worker',
            ServiceHeartbeat.valid_until > now,
        ).limit(1)
    )
    source = 'journal'
    if not observations:
        # The diagnostic UI must remain useful when its background observer is the
        # component that failed. Run the same bounded, read-only probes on demand.
        try:
            live = await collect_live_diagnostics()
            observations = [
                {
                    'resource': resource,
                    'status': result.status,
                    'observed_at': now.isoformat(),
                    'valid_until': now.isoformat(),
                    'latency_ms': round(result.latency_ms),
                    'safe_evidence': result.safe_evidence,
                }
                for resource, result in live.items()
            ]
            source = 'live_probe'
        except Exception:
            source = 'unavailable'
    return {
        'observations': observations,
        'observer_status': (
            'disabled' if not settings.deus_diagnostics_enabled
            else 'healthy' if observer_fresh
            else 'stale'
        ),
        'source': source,
        'unknown_without_recent_observation': not bool(observations),
    }
