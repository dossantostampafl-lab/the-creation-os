from __future__ import annotations

import pytest
from sqlalchemy import select
from test_knowledge import knowledge_db  # noqa: F401


@pytest.mark.asyncio
async def test_all_twelve_universes_discover_with_real_evidence_and_no_execution(knowledge_db):  # noqa: F811
    from app.admin.seed import CANONICAL_UNIVERSES
    from app.autonomy.discovery import KEYWORDS, DiscoveryWorker
    from app.knowledge.contracts import Candidate, Scope
    from app.knowledge.service import KnowledgeService
    from app.models.entities import Agent, Mission, Universe
    from app.models.opportunity import Opportunity
    factory, a, _ = knowledge_db
    from sqlalchemy import text
    async with factory() as session:
        await session.execute(text('TRUNCATE universes CASCADE'))
        for spec in CANONICAL_UNIVERSES:
            session.add(Universe(id=spec.id, code=spec.code, name=spec.name, active=True))
            await session.flush()
            session.add(Agent(code=spec.agent_code, name=spec.agent_name, universe_id=spec.id, active=True, capabilities_json={}))
            await KnowledgeService(session).write(Scope(creator_id=a), Candidate(title=spec.name, content='Necessidade registrada: '+KEYWORDS[spec.code][0]), 'signal:'+spec.code)
        await session.commit()
    worker = DiscoveryWorker(factory)
    report = await worker.run_once(a)
    assert report['universes_checked'] == 12
    assert report['discoveries'] == 12
    await worker.run_once(a)
    async with factory() as session:
        opportunities = list(await session.scalars(select(Opportunity)))
        assert len(opportunities) == 12
        assert all(row.evidence_refs_json for row in opportunities)
        assert not list(await session.scalars(select(Mission)))
