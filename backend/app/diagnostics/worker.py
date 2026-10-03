from __future__ import annotations

import asyncio
import fcntl
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

import httpx
from loguru import logger
from redis.asyncio import Redis
from sqlalchemy import exists, func, select, text

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.diagnostics.heartbeat import ServiceHeartbeat
from app.diagnostics.journal import DiagnosticJournal, JournalFull
from app.diagnostics.rules import DiagnosticRules
from app.knowledge.contracts import Candidate, Scope
from app.knowledge.service import KnowledgeService
from app.models.entities import Creator
from app.models.knowledge import KnowledgeItem, KnowledgeOutbox, KnowledgeReceipt, KnowledgeRevision


async def collect() -> dict[str,bool]:
    async def db_probe():
        async with AsyncSessionLocal() as session:
            await session.execute(text('SELECT 1'))
    async def redis_probe():
        redis=Redis.from_url(settings.redis_url, socket_timeout=2, socket_connect_timeout=2)
        try:
            await redis.ping()
        finally:
            await redis.aclose()
    async def api_probe():
        async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
            response=await client.get(os.environ.get('DIAGNOSTICS_API_URL','http://api:8000')+'/api/v1/health/ready')
            response.raise_for_status()
    async def worker_probe(resource):
        async with AsyncSessionLocal() as session:
            if not await session.scalar(select(ServiceHeartbeat.boot_id).where(
                ServiceHeartbeat.service==resource,
                ServiceHeartbeat.valid_until>datetime.now(timezone.utc)).limit(1)):
                raise RuntimeError('worker heartbeat stale')
    async def queue_probe():
        async with AsyncSessionLocal() as session:
            done = exists(select(KnowledgeReceipt.sequence).where(
                KnowledgeReceipt.sequence==KnowledgeOutbox.sequence, KnowledgeReceipt.consumer=='knowledge'))
            pending = await session.scalar(select(func.count()).select_from(KnowledgeOutbox).where(~done))
            if (pending or 0)>1000:
                raise RuntimeError('knowledge consumer backlog above threshold')
    async def disk_probe():
        stats = os.statvfs(settings.deus_diagnostics_root)
        if stats.f_bavail*stats.f_frsize < 64*1024*1024:
            raise RuntimeError('diagnostic volume free space below64MiB')
    async def bounded(call):
        try:
            async with asyncio.timeout(2):
                await call()
            return True
        except Exception:
            return False
    probes = {'PostgreSQL':db_probe, 'Redis':redis_probe, 'API':api_probe,
              'Fila da memória':queue_probe, 'Disco diagnóstico':disk_probe}
    if settings.deus_diagnostics_enabled:
        for resource in ['task-worker','knowledge-worker']:
            probes[resource] = partial(worker_probe, resource)
        if settings.deus_autonomy_discovery_enabled:
            probes['discovery-worker'] = lambda: worker_probe('discovery-worker')
    values = await asyncio.gather(*(bounded(probe) for probe in probes.values()))
    return dict(zip(probes, values))

async def creator_scope() -> str | None:
    async with AsyncSessionLocal() as session:
        if settings.sovereign_creator_id:
            return await session.scalar(select(Creator.id).where(Creator.id==settings.sovereign_creator_id,Creator.is_active.is_(True)))
        ids=list(await session.scalars(select(Creator.id).where(Creator.is_active.is_(True)).limit(2)))
        return ids[0] if len(ids)==1 else None

async def publish(journal: DiagnosticJournal, creator_id: str) -> None:
    for observation in journal.pending():
        async with AsyncSessionLocal() as session:
            valid_until=datetime.fromisoformat(observation['valid_until'])
            scope = Scope(creator_id=creator_id)
            service = KnowledgeService(session)
            # One current projection per resource/type. The immutable revisions and
            # local journal retain history; recovered incidents replace open ones.
            item_id = str(uuid.uuid5(uuid.NAMESPACE_URL,
                'creation:diagnostic:' + creator_id + ':' + observation['resource'] + ':' + observation['type']))
            await session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'),
                                  {'key': 'diagnostic-projection:' + item_id})
            previous = await session.scalar(select(KnowledgeRevision).join(
                KnowledgeItem, KnowledgeItem.current_revision_id == KnowledgeRevision.id).where(
                    KnowledgeItem.creator_id == creator_id, KnowledgeItem.active.is_(True),
                    KnowledgeRevision.source_type == 'manual', KnowledgeRevision.source_id == item_id))
            older = previous and json.loads(previous.content)['observed_at'] >= observation['observed_at']
            if not older:
                await service.write(scope, Candidate(
                    title='Diagnóstico: ' + observation['resource'],
                    content=json.dumps(observation, ensure_ascii=False), kind='diagnostic',
                    valid_until=valid_until, source_id=item_id), 'diagnostic:' + observation['id'],
                    previous.item_id if previous else None, previous.id if previous else None)
            await session.commit()
        journal.ack(observation['id'])

async def run() -> None:
    if not settings.deus_diagnostics_enabled:
        logger.info('diagnostics disabled by configuration')
        return
    journal=DiagnosticJournal(Path(settings.deus_diagnostics_root))
    rules=DiagnosticRules()
    stored=journal.get_rules()
    for row in stored.values():
        for key in ['observed_at','valid_until']:
            if key in row:
                row[key]=datetime.fromisoformat(row[key])
    rules.states=stored
    while True:
        now=datetime.now(timezone.utc)
        observations=await collect()
        for resource,healthy in observations.items():
            incident=rules.observe(resource,healthy,now)
            observation={'id':str(uuid.uuid4()),'type':'observation','resource':resource,'status':'healthy' if healthy else 'unhealthy','observed_at':now.isoformat(),'valid_until':(now+timedelta(seconds=45)).isoformat()}
            try:
                journal.append(observation)
                if incident:
                    journal.append({**observation,**incident,'id':str(uuid.uuid4()),'type':'incident'})
            except JournalFull:
                logger.error('diagnostic journal full; new evidence admission stopped')
        saved={key:{k:v.isoformat() if isinstance(v,datetime) else v for k,v in row.items()} for key,row in rules.states.items()}
        journal.set_rules(saved)
        try:
            creator_id=await creator_scope()
            if creator_id:
                journal.bind_creator(creator_id)
                await publish(journal,creator_id)
        except Exception as exc:
            logger.bind(component='diagnostics',error_type=type(exc).__name__).warning('diagnostics retained locally for replay')
        await asyncio.sleep(15)

if __name__=='__main__':
    root=Path(settings.deus_diagnostics_root)
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (root/'.worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        asyncio.run(run())
