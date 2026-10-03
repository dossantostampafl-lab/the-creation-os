from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def knowledge_db():
    engine = create_async_engine(os.environ['DATABASE_URL'])
    async with engine.begin() as conn:
        await conn.execute(text('TRUNCATE creator RESTART IDENTITY CASCADE'))
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        await conn.execute(text("INSERT INTO creator(id,username,password_hash,is_active) VALUES (:a,'a','unused',true),(:b,'b','unused',true)"), {'a': a, 'b': b})
    yield async_sessionmaker(engine, expire_on_commit=False), a, b
    await engine.dispose()


@pytest.mark.asyncio
async def test_knowledge_versioning_scope_and_idempotency(knowledge_db):
    from app.knowledge.contracts import Candidate, Scope
    from app.knowledge.service import KnowledgeConflict, KnowledgeService
    factory, a, b = knowledge_db
    async with factory() as session:
        service = KnowledgeService(session)
        candidate = Candidate(title='Voz do DEUS', content='Voz local Kokoro e Vosk', kind='decision')
        first = await service.write(Scope(creator_id=a), candidate, 'choice-1')
        same = await service.write(Scope(creator_id=a), candidate, 'choice-1')
        assert same.revision_id == first.revision_id
        with pytest.raises(KnowledgeConflict):
            await service.write(Scope(creator_id=a), candidate.model_copy(update={'content': 'Outra voz'}), 'choice-1')
        await session.commit()
    async with factory() as session:
        service = KnowledgeService(session)
        assert await service.get(Scope(creator_id=b), first.item_id) is None
        found = await service.search(Scope(creator_id=a), 'Kokoro')
        assert found.evidences[0].content == candidate.content
        await service.revoke(Scope(creator_id=a), first.item_id, first.revision_id)
        await session.commit()
    async with factory() as session:
        assert not (await KnowledgeService(session).search(Scope(creator_id=a), 'Kokoro')).evidences


@pytest.mark.asyncio
async def test_knowledge_dependencies_and_verified_require_evidence(knowledge_db):
    from app.knowledge.contracts import Candidate, Scope
    from app.knowledge.service import KnowledgeConflict, KnowledgeService
    factory, a, b = knowledge_db
    async with factory() as session:
        service = KnowledgeService(session)
        original = await service.write(Scope(creator_id=a), Candidate(title='Teste', content='Kokoro confirmado'), 'orig')
        derived = await service.write(Scope(creator_id=a), Candidate(title='Resumo', content='Resumo Kokoro', dependencies=[original.revision_id]), 'der')
        with pytest.raises(KnowledgeConflict):
            await service.write(Scope(creator_id=b), Candidate(title='Vazamento', content='Private', dependencies=[original.revision_id]), 'bad-owner')
        with pytest.raises(KnowledgeConflict):
            await service.write(Scope(creator_id=a), Candidate(title='Palpite', content='Tudo funciona', epistemic_state='verified'), 'no-evidence')
        await service.revoke(Scope(creator_id=a), original.item_id, original.revision_id)
        await session.commit()
    async with factory() as session:
        assert not (await KnowledgeService(session).search(Scope(creator_id=a), 'Resumo')).evidences
        assert derived.item_id != original.item_id


@pytest.mark.asyncio
async def test_indexer_receipts_do_not_lose_late_commits(knowledge_db):
    from app.knowledge.contracts import Candidate, Scope
    from app.knowledge.indexer import process_batch
    from app.knowledge.service import KnowledgeService
    factory, a, b = knowledge_db
    async with factory() as slow, factory() as fast:
        await KnowledgeService(slow).write(Scope(creator_id=a), Candidate(title='Lento', content='late'), 'slow')
        await KnowledgeService(fast).write(Scope(creator_id=b), Candidate(title='Rápido', content='fast'), 'fast')
        await fast.commit()
        assert await process_batch(factory) == 1
        await slow.commit()
        assert await process_batch(factory) == 1
        assert await process_batch(factory) == 0


@pytest.mark.asyncio
async def test_source_changes_invalidate_before_indexer(knowledge_db):
    from app.knowledge.contracts import Candidate, Scope
    from app.knowledge.service import KnowledgeService
    from app.models.entities import Conversation, Message
    factory, a, _ = knowledge_db
    async with factory() as session:
        conversation = Conversation(id=str(uuid.uuid4()), creator_id=a, title='History', status='active')
        session.add(conversation)
        await session.flush()
        message = Message(id=str(uuid.uuid4()), conversation_id=conversation.id, role='creator', content='Kokoro escolhido', actor_id=a, route='deus', metadata_json={}, correlation_id=str(uuid.uuid4()))
        session.add(message)
        await session.flush()
        await KnowledgeService(session).write(Scope(creator_id=a), Candidate(title='Escolha', content=message.content, source_type='message', source_id=message.id), 'source')
        await session.commit()
        message.content = 'Escolha revogada'
        await session.commit()
    async with factory() as session:
        assert not (await KnowledgeService(session).search(Scope(creator_id=a), 'Kokoro')).evidences


@pytest.mark.asyncio
async def test_obsidian_recovers_replace_crash_and_revocation(knowledge_db, tmp_path):
    from app.knowledge.contracts import Candidate, Scope
    from app.knowledge.obsidian import ObsidianExporter
    from app.knowledge.service import KnowledgeService
    factory, a, _ = knowledge_db
    async with factory() as session:
        original = await KnowledgeService(session).write(Scope(creator_id=a), Candidate(title='../Título', content='Voz Kokoro'), 'note')
        await session.commit()
    exporter = ObsidianExporter(factory, tmp_path)
    report = await exporter.export(Scope(creator_id=a))
    assert report['written'] == 1
    note = tmp_path / a / 'document' / (original.item_id + '.md')
    assert 'Voz Kokoro' in note.read_text()
    note.write_text('Edição humana privada')
    async with factory() as session:
        await KnowledgeService(session).revoke(Scope(creator_id=a), original.item_id, original.revision_id)
        await session.commit()
    report = await exporter.export(Scope(creator_id=a))
    assert not note.exists()
    assert report['conflicts'] == 1
    assert (tmp_path / a / '.quarantine' / note.name).read_text() == 'Edição humana privada'
    assert (await exporter.export(Scope(creator_id=a)))['written'] == 0


@pytest.mark.asyncio
async def test_obsidian_recovers_after_file_replaced_before_manifest(knowledge_db, tmp_path, monkeypatch):
    from app.knowledge.contracts import Candidate, Scope
    from app.knowledge.service import KnowledgeService
    from app.knowledge import obsidian
    factory, a, _ = knowledge_db
    async with factory() as session:
        note = await KnowledgeService(session).write(Scope(creator_id=a), Candidate(title='Crash', content='Kokoro'), 'crash')
        await session.commit()
    original = obsidian.atomic_write
    def fail_after_replace(path, content):
        original(path, content)
        raise OSError('simulated crash after replace')
    monkeypatch.setattr(obsidian, 'atomic_write', fail_after_replace)
    with pytest.raises(OSError):
        await obsidian.ObsidianExporter(factory, tmp_path).export(Scope(creator_id=a))
    monkeypatch.setattr(obsidian, 'atomic_write', original)
    assert (await obsidian.ObsidianExporter(factory, tmp_path).export(Scope(creator_id=a)))['conflicts'] == 0
    assert (tmp_path / a / 'document' / (note.item_id + '.md')).exists()
