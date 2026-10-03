from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from test_knowledge import knowledge_db  # noqa: F401


def test_incident_hysteresis_and_stale_observations():
    from app.diagnostics.rules import DiagnosticRules
    rules = DiagnosticRules()
    now = datetime.now(timezone.utc)
    assert rules.observe('db', False, now) is None
    assert rules.observe('db', False, now) is None
    assert rules.observe('db', False, now)['state'] == 'open'
    assert rules.observe('db', False, now) is None
    assert rules.observe('db', True, now) is None
    assert rules.observe('db', True, now)['state'] == 'recovered'
    assert rules.current('db', now + timedelta(seconds=46))['status'] == 'unknown'


def test_diagnostic_journal_replays_until_ack_and_survives_restart(tmp_path):
    from app.diagnostics.journal import DiagnosticJournal
    journal = DiagnosticJournal(tmp_path)
    journal.append({'id':'one', 'resource':'db', 'status':'unhealthy'})
    journal.append({'id':'one', 'resource':'db', 'status':'unhealthy'})
    assert len(journal.pending()) == 1
    reopened = DiagnosticJournal(tmp_path)
    assert reopened.pending()[0]['id'] == 'one'
    reopened.ack('one')
    assert not reopened.pending()


def test_journal_capacity_is_explicit(tmp_path):
    from app.diagnostics.journal import DiagnosticJournal, JournalFull
    journal = DiagnosticJournal(tmp_path, max_bytes=100)
    with pytest.raises(JournalFull):
        journal.append({'id':'big', 'data':'x'*200})
    assert (tmp_path/'spool-full.json').exists()


@pytest.mark.asyncio
async def test_projection_replaces_incident_and_replays_after_ack_loss(knowledge_db, monkeypatch, tmp_path):  # noqa: F811
    import uuid

    from sqlalchemy import select

    from app.diagnostics import worker
    from app.diagnostics.journal import DiagnosticJournal
    from app.models.knowledge import KnowledgeItem, KnowledgeRevision
    factory, a, _ = knowledge_db
    monkeypatch.setattr(worker, 'AsyncSessionLocal', factory)
    journal = DiagnosticJournal(tmp_path)
    now = datetime.now(timezone.utc)
    for index, state in enumerate(['open', 'recovered']):
        observation = {'id':str(uuid.uuid4()),'type':'incident','resource':'PostgreSQL','state':state,
                       'observed_at':(now+timedelta(seconds=index)).isoformat(),
                       'valid_until':(now+timedelta(seconds=45+index)).isoformat()}
        journal.append(observation)
        original = journal.ack
        monkeypatch.setattr(journal, 'ack', lambda _: None)
        await worker.publish(journal, a)
        await worker.publish(journal, a)
        monkeypatch.setattr(journal, 'ack', original)
        await worker.publish(journal, a)
    async with factory() as session:
        items = list(await session.scalars(select(KnowledgeItem).where(KnowledgeItem.creator_id==a)))
        assert len(items)==1
        revision = await session.get(KnowledgeRevision, items[0].current_revision_id)
        assert 'recovered' in revision.content
        assert revision.valid_until is not None


@pytest.mark.asyncio
async def test_worker_heartbeat_records_boot_and_expires(knowledge_db, monkeypatch):  # noqa: F811
    import asyncio

    from sqlalchemy import select

    from app.config import settings
    from app.diagnostics import heartbeat
    factory, _, _ = knowledge_db
    monkeypatch.setattr(settings, 'deus_diagnostics_enabled', True)
    monkeypatch.setattr(heartbeat, 'AsyncSessionLocal', factory)
    async def run():
        await asyncio.sleep(.1)
    await heartbeat.supervised('test-worker', run)
    async with factory() as session:
        row = await session.scalar(select(heartbeat.ServiceHeartbeat).where(heartbeat.ServiceHeartbeat.service=='test-worker'))
        assert row.boot_id==row.lease_owner
        assert 0 < (row.valid_until-row.observed_at).total_seconds() <= 45


@pytest.mark.asyncio
async def test_context_reads_only_recent_diagnostics_and_tracks_dependencies(knowledge_db):  # noqa: F811
    import json
    import uuid

    from app.diagnostics.context import current_diagnostics
    from app.knowledge.contracts import Candidate, Scope
    from app.knowledge.service import KnowledgeService
    from app.models.entities import Conversation
    from app.services.deus_context import DeusContextBuilder
    factory, a, _ = knowledge_db
    now = datetime.now(timezone.utc)
    async with factory() as session:
        conversation = Conversation(id=str(uuid.uuid4()),creator_id=a,title='Diagnóstico',status='active')
        session.add(conversation)
        service = KnowledgeService(session)
        current = await service.write(Scope(creator_id=a), Candidate(title='Redis', kind='diagnostic', valid_until=now+timedelta(seconds=45),content=json.dumps({'type':'observation','resource':'Redis','status':'healthy','observed_at':now.isoformat(),'valid_until':(now+timedelta(seconds=45)).isoformat()})), 'current')
        await service.write(Scope(creator_id=a), Candidate(title='DB antiga', kind='diagnostic',valid_until=now-timedelta(seconds=1),content=json.dumps({'type':'observation','resource':'DB antiga','status':'healthy'})), 'old')
        await session.commit()
        observed = await current_diagnostics(session,a)
        assert [row['resource'] for row in observed]==['Redis']
    packet = await DeusContextBuilder(factory).build(a,conversation.id,'Como está o sistema?', 'voice')
    assert current.revision_id in packet.trace['dependency_revision_ids']
    assert any('Redis' in row['content'] for row in packet.messages)
