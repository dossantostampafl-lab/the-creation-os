from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from datetime import datetime, timezone

from sqlalchemy import func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.contracts import Candidate, Evidence, RetrievalResult, Scope, Written
from app.models.entities import Conversation, Creator, Message, Mission, Task, uuid_string
from app.models.knowledge import (
    KnowledgeDependency,
    KnowledgeEpoch,
    KnowledgeItem,
    KnowledgeOutbox,
    KnowledgeProject,
    KnowledgeRelation,
    KnowledgeRevision,
)
from app.observability.telemetry import traced


class KnowledgeConflict(ValueError):
    pass

def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()

class KnowledgeService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def source_hash(self, scope: Scope, source_type: str, source_id: str | None) -> str | None:
        if source_type == "manual":
            return None
        if source_type == "message":
            row = (await self.session.execute(select(Message.content).join(Conversation, Conversation.id == Message.conversation_id).where(Message.id == source_id, Conversation.creator_id == scope.creator_id))).first()
            return digest(row[0]) if row else None
        if source_type == "mission":
            row = await self.session.scalar(select(Mission).where(Mission.id == source_id, Mission.creator_id == scope.creator_id))
            return digest(json.dumps([row.title, row.objective, row.status])) if row else None
        if source_type == "task":
            row = await self.session.scalar(select(Task).join(Mission, Mission.id == Task.mission_id).where(Task.id == source_id, Mission.creator_id == scope.creator_id))
            return digest(json.dumps([row.status, row.output_json, row.error_json], sort_keys=True)) if row else None
        if source_type in {"diagnostic_observation", "diagnostic_incident"}:
            return digest(f"{scope.creator_id}:{source_type}:{source_id}") if source_id else None
        return None

    async def eligible(self, scope: Scope, revision: KnowledgeRevision, seen: set[str] | None = None, depth: int = 0) -> bool:
        seen = set() if seen is None else set(seen)
        if revision.id in seen or depth > 8 or revision.creator_id != scope.creator_id or revision.lifecycle != "active":
            return False
        seen.add(revision.id)
        item = await self.session.get(KnowledgeItem, revision.item_id)
        if not item or not item.active or item.current_revision_id != revision.id:
            return False
        if revision.valid_until and revision.valid_until <= datetime.now(timezone.utc):
            return False
        if revision.source_type != "manual" and await self.source_hash(scope, revision.source_type, revision.source_id) != revision.source_hash:
            return False
        dependencies = list(await self.session.scalars(select(KnowledgeDependency.source_revision_id).where(KnowledgeDependency.revision_id == revision.id)))
        if len(dependencies) > 32:
            return False
        for dependency in dependencies:
            parent = await self.session.get(KnowledgeRevision, dependency)
            if not parent or not await self.eligible(scope, parent, seen, depth + 1):
                return False
        return True

    async def get(self, scope: Scope, item_id: str) -> KnowledgeRevision | None:
        item = await self.session.scalar(select(KnowledgeItem).where(KnowledgeItem.id == item_id, KnowledgeItem.creator_id == scope.creator_id))
        return await self.session.get(KnowledgeRevision, item.current_revision_id) if item else None

    async def write(self, scope: Scope, candidate: Candidate, key: str, item_id: str | None = None, expected_revision_id: str | None = None) -> Written:
        if not key or len(key) > 200:
            raise KnowledgeConflict("invalid idempotency key")
        if len(candidate.content.encode()) > 262144:
            raise KnowledgeConflict("source exceeds 256 KiB")
        # All import paths share one canonical message source, including revoked sources.
        if candidate.source_type == "message" and candidate.source_id and item_id is None:
            await self.session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": scope.creator_id + ':message-source:' + candidate.source_id})
        canonical = candidate.model_dump(mode="json")
        fingerprint = digest(json.dumps([canonical, item_id, expected_revision_id], sort_keys=True, ensure_ascii=False))
        # Serialize matching requests only; this lock is transaction scoped and never held over inference.
        await self.session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": scope.creator_id + ':' + key})
        existing = await self.session.scalar(select(KnowledgeOutbox).where(KnowledgeOutbox.creator_id == scope.creator_id, KnowledgeOutbox.request_key == key))
        if existing:
            if existing.payload_hash != fingerprint:
                raise KnowledgeConflict("idempotency key has a different payload")
            return Written(item_id=existing.item_id, revision_id=existing.revision_id)
        if candidate.source_type == "message" and candidate.source_id and item_id is None:
            prior = await self.session.scalar(select(KnowledgeRevision).where(
                KnowledgeRevision.creator_id == scope.creator_id,
                KnowledgeRevision.source_type == "message",
                KnowledgeRevision.source_id == candidate.source_id).order_by(KnowledgeRevision.ordinal.desc()).limit(1))
            if prior is not None:
                self.session.add(KnowledgeOutbox(creator_id=scope.creator_id, request_key=key,
                    payload_hash=fingerprint, item_id=prior.item_id, revision_id=prior.id))
                await self.session.flush()
                return Written(item_id=prior.item_id, revision_id=prior.id)
        creator = await self.session.get(Creator, scope.creator_id)
        if not creator or not creator.is_active:
            raise KnowledgeConflict("Creator unavailable")
        if candidate.project_id:
            project = await self.session.scalar(select(KnowledgeProject).where(KnowledgeProject.id == candidate.project_id, KnowledgeProject.creator_id == scope.creator_id))
            if not project:
                raise KnowledgeConflict("project unavailable")
        source_hash = await self.source_hash(scope, candidate.source_type, candidate.source_id)
        if candidate.source_type != "manual" and source_hash is None:
            raise KnowledgeConflict("source unavailable in Creator scope")
        parents = []
        for dep in set(candidate.dependencies):
            parent = await self.session.get(KnowledgeRevision, dep)
            if not parent or not await self.eligible(scope, parent):
                raise KnowledgeConflict("dependency unavailable")
            parents.append(parent)
        if candidate.epistemic_state == "verified":
            # Verification is grounded in completed domain execution, never in a model claim.
            task = await self.session.get(Task, candidate.source_id) if candidate.source_type == "task" else None
            if not task or task.status != "SUCCEEDED":
                raise KnowledgeConflict("verified knowledge requires successful domain execution")
        item = None
        ordinal = 1
        if item_id:
            item = await self.session.scalar(select(KnowledgeItem).where(KnowledgeItem.id == item_id, KnowledgeItem.creator_id == scope.creator_id).with_for_update())
            if not item or not item.active or item.current_revision_id != expected_revision_id:
                raise KnowledgeConflict("revision conflict or unavailable item")
            previous = await self.session.get(KnowledgeRevision, item.current_revision_id)
            assert previous
            ordinal = previous.ordinal + 1
            if any(p.item_id == item_id for p in parents):
                raise KnowledgeConflict("cyclic dependency")
        revision_id = uuid_string()
        if item is None:
            item = KnowledgeItem(id=uuid_string(), creator_id=scope.creator_id, project_id=candidate.project_id, current_revision_id=revision_id, active=True)
            self.session.add(item)
            await self.session.flush()
        item.current_revision_id = revision_id
        revision = KnowledgeRevision(id=revision_id, creator_id=scope.creator_id, item_id=item.id, ordinal=ordinal, title=candidate.title, content=unicodedata.normalize("NFC", candidate.content), kind=candidate.kind, epistemic_state=candidate.epistemic_state, lifecycle="active", source_type=candidate.source_type, source_id=candidate.source_id, source_hash=source_hash, content_hash=digest(candidate.content), valid_until=candidate.valid_until)
        self.session.add(revision)
        await self.session.flush()
        for parent in parents:
            self.session.add(KnowledgeDependency(revision_id=revision_id, source_revision_id=parent.id, creator_id=scope.creator_id))
        self.session.add(KnowledgeOutbox(creator_id=scope.creator_id, request_key=key, payload_hash=fingerprint, item_id=item.id, revision_id=revision_id))
        await self.bump(scope.creator_id)
        await self.session.flush()
        return Written(item_id=item.id, revision_id=revision_id)

    async def bump(self, creator_id: str) -> None:
        stmt = insert(KnowledgeEpoch).values(creator_id=creator_id, version=1)
        await self.session.execute(stmt.on_conflict_do_update(index_elements=['creator_id'], set_={'version': KnowledgeEpoch.version + 1}))

    async def revoke(self, scope: Scope, item_id: str, expected_revision_id: str) -> Written:
        item = await self.session.scalar(select(KnowledgeItem).where(KnowledgeItem.id == item_id, KnowledgeItem.creator_id == scope.creator_id).with_for_update())
        if not item or item.current_revision_id != expected_revision_id:
            raise KnowledgeConflict("revision conflict")
        previous = await self.session.get(KnowledgeRevision, item.current_revision_id)
        assert previous
        tombstone = KnowledgeRevision(id=uuid_string(), item_id=item.id, creator_id=scope.creator_id, ordinal=previous.ordinal + 1, title=previous.title, content="", kind=previous.kind, epistemic_state=previous.epistemic_state, lifecycle="revoked", source_type="manual", content_hash=digest(""))
        self.session.add(tombstone)
        await self.session.flush()
        item.current_revision_id = tombstone.id
        item.active = False
        self.session.add(KnowledgeOutbox(creator_id=scope.creator_id, request_key='revoke:' + tombstone.id, payload_hash=digest(tombstone.id), item_id=item.id, revision_id=tombstone.id))
        await self.bump(scope.creator_id)
        await self.session.flush()
        return Written(item_id=item.id, revision_id=tombstone.id)

    @traced("deus.knowledge.search")
    async def search(self, scope: Scope, query: str) -> RetrievalResult:
        started = time.perf_counter()
        if not query.strip() or len(query) > 2048:
            return RetrievalResult(status="empty")
        await self.session.execute(text("SET LOCAL statement_timeout = '200ms'"))
        terms = re.findall(r'[\w-]+', query, flags=re.UNICODE)[:30]
        q = func.websearch_to_tsquery('portuguese', ' OR '.join(terms))
        rank = func.ts_rank_cd(KnowledgeRevision.search_vector, q)
        literal = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        statement = select(KnowledgeRevision).join(KnowledgeItem, KnowledgeItem.current_revision_id == KnowledgeRevision.id).where(KnowledgeItem.creator_id == scope.creator_id, KnowledgeItem.active.is_(True), or_(KnowledgeRevision.search_vector.op('@@')(q), KnowledgeRevision.content.ilike(literal), KnowledgeRevision.title.ilike(literal))).order_by(rank.desc(), KnowledgeRevision.created_at.desc()).limit(30)
        if scope.project_id:
            statement = statement.where(KnowledgeItem.project_id == scope.project_id)
        rows = list(await self.session.scalars(statement))
        evidence = []
        for row in rows:
            if await self.eligible(scope, row):
                evidence.append(Evidence(item_id=row.item_id, revision_id=row.id, title=row.title, content=row.content[:1500], kind=row.kind, epistemic_state=row.epistemic_state, source_type=row.source_type, source_id=row.source_id, observed_at=row.created_at, valid_until=row.valid_until))
            if len(evidence) == 6:
                break
        if evidence:
            roots = [entry.item_id for entry in evidence[:3]]
            related = select(KnowledgeRevision).join(KnowledgeItem,
                KnowledgeItem.current_revision_id==KnowledgeRevision.id).join(KnowledgeRelation,
                KnowledgeRelation.to_id==KnowledgeItem.id).where(
                    KnowledgeRelation.creator_id==scope.creator_id, KnowledgeRelation.from_id.in_(roots),
                    KnowledgeItem.creator_id==scope.creator_id, KnowledgeItem.active.is_(True),
                    KnowledgeItem.id.not_in([entry.item_id for entry in evidence])).order_by(
                        KnowledgeRevision.created_at.desc()).limit(3)
            if scope.project_id:
                related = related.where(KnowledgeItem.project_id==scope.project_id)
            links = []
            linked_ids: set[str] = set()
            for row in await self.session.scalars(related):
                if row.item_id not in linked_ids and await self.eligible(scope, row):
                    linked_ids.add(row.item_id)
                    links.append(Evidence(item_id=row.item_id, revision_id=row.id, title=row.title,
                        content=row.content[:1500], kind=row.kind, epistemic_state=row.epistemic_state,
                        source_type=row.source_type, source_id=row.source_id, observed_at=row.created_at,
                        valid_until=row.valid_until))
            evidence = (evidence[:3] + links + evidence[3:])[:6]
        epoch = await self.session.scalar(select(KnowledgeEpoch.version).where(KnowledgeEpoch.creator_id == scope.creator_id)) or 0
        return RetrievalResult(status="ok" if evidence else "empty", evidences=evidence, knowledge_epoch=epoch, elapsed_ms=(time.perf_counter()-started)*1000)
