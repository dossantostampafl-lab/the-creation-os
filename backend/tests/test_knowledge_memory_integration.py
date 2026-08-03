"""Lote 2.5, section 2's central problem, proven end-to-end: KnowledgeResearchAgent
consults real Conscious Memory (not a fake/mock) through the pattern-(a) seam in
AgentExecutionService.run() — memory is resolved *outside* the handler and merged
into its payload — and its output genuinely reflects what was consulted.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from db_safety import create_isolated_test_engine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.domain import Actor
from app.models.entities import Agent, AgentCapability, Capability, Conversation, Creator, Inception, Message, Mission, Task
from app.repositories.conscious_memory import ConsciousMemoryRepository
from app.repositories.dispatch import DispatchRepository
from app.repositories.execution import ExecutionRepository
from app.repositories.tree_core import TreeCoreRepository
from app.repositories.workers import WorkerRepository
from app.services.conscious_memory import ConsciousMemoryService
from app.services.dispatch import DispatchService
from app.services.execution import AgentExecutionService
from app.services.tree_core import TreeCoreService
from app.services.workers import WorkerService

pytestmark = pytest.mark.integration


@pytest.fixture
async def knowledge_memory_db():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE conscious_memory, worker_capabilities, workers, dispatch_attempts, dispatch_items, "
                "task_dependencies, tasks, agent_capabilities, capabilities, agents, universes, chronicles, "
                "mission_plans, missions, inceptions, messages, conversations, creator RESTART IDENTITY CASCADE"
            )
        )
    ids = {key: str(uuid.uuid4()) for key in ("creator", "conversation", "message", "inception", "mission", "capability", "agent", "task")}
    now = datetime.now(timezone.utc)
    async with factory() as session:
        session.add(Creator(id=ids["creator"], username="creator", password_hash="unused", is_active=True))
        await session.commit()
        session.add(Conversation(id=ids["conversation"], creator_id=ids["creator"], title="km", status="active"))
        await session.commit()
        session.add(
            Message(
                id=ids["message"], conversation_id=ids["conversation"], role="creator", actor_id=ids["creator"],
                correlation_id=str(uuid.uuid4()), content="x", route="central", metadata_json={},
            )
        )
        await session.commit()
        session.add(
            Inception(
                id=ids["inception"], conversation_id=ids["conversation"], source_message_id=ids["message"],
                title="Knowledge", description="knowledge memory integration", status="approved", trinity_assessment_json={},
            )
        )
        await session.commit()
        session.add(
            Mission(
                id=ids["mission"], inception_id=ids["inception"], creator_id=ids["creator"], title="Mission",
                objective="Research", status="authorized", authorization_json={},
            )
        )
        session.add(Capability(id=ids["capability"], name="knowledge_research", description=""))
        session.add(
            Agent(
                id=ids["agent"], name="Knowledge Research Agent", description="", universe_name="knowledge", active=True,
                capabilities_json={}, priority=1, status="idle", version=1, heartbeat_at=now, enabled=True,
            )
        )
        await session.commit()
        session.add(AgentCapability(agent_id=ids["agent"], capability_id=ids["capability"]))
        session.add(
            Task(
                id=ids["task"], mission_id=ids["mission"], name="Research", description="Research", required_capability_id=ids["capability"],
                priority=1, state="ready", retry_limit=1, retry_count=0, timeout_seconds=30, status="PENDING",
                # First 8 chars ("Trinity ") deliberately match the seeded ConsciousMemory
                # content below so FakeEmbeddingModel (which only looks at the first 8
                # characters) produces identical embeddings — a deterministic top match,
                # not a flaky similarity ranking.
                input_json={"topic": "Trinity orchestration policy", "notes": ["Existing note"]},
                output_json={}, error_json={}, attempt_count=0, max_attempts=1, idempotency_key=str(uuid.uuid4()),
            )
        )
        await session.commit()
    yield factory, ids
    await engine.dispose()


@pytest.mark.asyncio
async def test_knowledge_research_handler_reflects_real_consolidated_memory(knowledge_memory_db):
    factory, ids = knowledge_memory_db

    # Seed real Conscious Memory via an explicit-decision consolidation (trigger
    # (ii)) — not a fake/mock repository, a real Postgres row.
    async with factory() as session:
        memory_service = ConsciousMemoryService(ConsciousMemoryRepository(session))
        seeded = await memory_service.consolidate_explicit(
            Actor(id=ids["creator"], role="creator"),
            source_type="creator_decision",
            source_id=ids["mission"],
            content="Trinity orchestration policy: prefer REQUIRES_CREATOR on ambiguous risk.",
            correlation_id=str(uuid.uuid4()),
        )

    async with factory() as session:
        dispatch = DispatchService(DispatchRepository(session), TreeCoreService(TreeCoreRepository(session)))
        workers = WorkerService(WorkerRepository(session), dispatch)
        worker, token = await workers.register(str(uuid.uuid4()), "knowledge-worker", "1.0", ["knowledge_research"])
        await workers.heartbeat(worker, "1.0", "available")
        await dispatch.enqueue(ids["creator"], ids["task"], priority=1, max_attempts=1)
        item, lease_token, _capability_name = await workers.claim(worker, 60)
        assert item is not None

        execution_service = AgentExecutionService(ExecutionRepository(session), dispatch)
        execution = await execution_service.create(worker, item.id, lease_token, "knowledge_research", "1.0")
        await execution_service.accept(execution.id, worker, lease_token)
        finished = await execution_service.run(execution.id, worker, lease_token)

    assert finished.state == "succeeded"
    output = finished.output_payload
    memory_note = f"[conscious-memory:{seeded.id}] {seeded.content}"
    assert memory_note in output["key_points"], output["key_points"]
    assert "Existing note" in output["key_points"]  # the Task's own note is preserved, not replaced
    # The handler's own `sources` field is unchanged (it always cites
    # internal-memory:mission/task ids) — the Conscious Memory provenance is
    # carried instead in the key_points entry itself (the "[conscious-memory:{id}]"
    # prefix asserted above), since the handler stays untouched by this lote.
    assert output["sources"] == [f"internal-memory:mission:{ids['mission']}", f"internal-memory:task:{ids['task']}"]


@pytest.mark.asyncio
async def test_knowledge_research_runs_normally_with_no_matching_memory(knowledge_memory_db):
    """No Conscious Memory rows exist at all — the handler still succeeds using
    only the Task's own notes, proving memory augmentation is additive, not
    required."""
    factory, ids = knowledge_memory_db
    async with factory() as session:
        dispatch = DispatchService(DispatchRepository(session), TreeCoreService(TreeCoreRepository(session)))
        workers = WorkerService(WorkerRepository(session), dispatch)
        worker, token = await workers.register(str(uuid.uuid4()), "knowledge-worker", "1.0", ["knowledge_research"])
        await workers.heartbeat(worker, "1.0", "available")
        await dispatch.enqueue(ids["creator"], ids["task"], priority=1, max_attempts=1)
        item, lease_token, _capability_name = await workers.claim(worker, 60)

        execution_service = AgentExecutionService(ExecutionRepository(session), dispatch)
        execution = await execution_service.create(worker, item.id, lease_token, "knowledge_research", "1.0")
        await execution_service.accept(execution.id, worker, lease_token)
        finished = await execution_service.run(execution.id, worker, lease_token)

    assert finished.state == "succeeded"
    assert finished.output_payload["key_points"] == ["Existing note"]
