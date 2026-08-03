"""Lote 2.5, section 3: Conscious Memory consolidation must only happen via
(i) a mission reaching MANIFESTED for the first time, or (ii) an explicit
Creator decision — never as a side effect of any other step in the mission
tail (consolidate/decide) or of running a handler. Reuses `consolidation_db`
from test_consolidation_integration.py, the same fixture
test_worker_orchestration.py already reuses for tail-orchestration coverage:
a Mission already EXECUTING with two fully-executed, consolidation-ready
tasks.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from test_consolidation_integration import consolidation_db  # noqa: F401  (reused fixture)

from app.models.entities import ConsciousMemory
from app.repositories.conscious_memory import ConsciousMemoryRepository
from app.repositories.consolidation import ConsolidationRepository
from app.repositories.decision import DecisionRepository
from app.repositories.manifestation import ManifestationRepository
from app.services.conscious_memory import ConsciousMemoryService
from app.services.consolidation import ConsolidationService
from app.services.decision import DecisionService
from app.services.manifestation import ManifestationService

pytestmark = pytest.mark.integration


async def _conscious_memory_count_for(factory, mission_id: str) -> int:
    async with factory() as session:
        return await session.scalar(
            select(func.count()).select_from(ConsciousMemory).where(ConsciousMemory.source_id == mission_id)
        )


@pytest.mark.asyncio
async def test_consolidate_and_decide_alone_never_create_conscious_memory(consolidation_db):  # noqa: F811
    """Running the first two tail steps (consolidate, decide) without the
    third (manifest) must leave Conscious Memory untouched — proving
    consolidation isn't a side effect of the mission-tail machinery in
    general, only of manifestation specifically."""
    factory, ids = consolidation_db
    correlation_id = str(uuid.uuid4())

    async with factory() as session:
        consolidation, _ = await ConsolidationService(ConsolidationRepository(session)).consolidate(
            ids["mission"], correlation_id=correlation_id, actor_id="test", actor_role="worker"
        )
    assert await _conscious_memory_count_for(factory, ids["mission"]) == 0

    async with factory() as session:
        await DecisionService(DecisionRepository(session)).decide(
            ids["mission"], correlation_id=correlation_id, actor_id="test", actor_role="worker",
            causation_id=consolidation.id,
        )
    assert await _conscious_memory_count_for(factory, ids["mission"]) == 0


@pytest.mark.asyncio
async def test_manifestation_consolidates_exactly_once_and_only_on_first_success(consolidation_db):  # noqa: F811
    """Trigger (i): manifest() creates exactly one Conscious Memory row on the
    first (real) manifestation, and calling manifest() again (idempotent
    repeat) does not create a second one."""
    factory, ids = consolidation_db
    correlation_id = str(uuid.uuid4())

    async with factory() as session:
        consolidation, _ = await ConsolidationService(ConsolidationRepository(session)).consolidate(
            ids["mission"], correlation_id=correlation_id, actor_id="test", actor_role="worker"
        )
    async with factory() as session:
        decision, _ = await DecisionService(DecisionRepository(session)).decide(
            ids["mission"], correlation_id=correlation_id, actor_id="test", actor_role="worker",
            causation_id=consolidation.id,
        )
    assert await _conscious_memory_count_for(factory, ids["mission"]) == 0

    async with factory() as session:
        manifestation, created = await ManifestationService(ManifestationRepository(session)).manifest(
            ids["mission"], correlation_id=correlation_id, actor_id="test", actor_role="worker",
            causation_id=decision.id,
        )
    assert created is True
    assert await _conscious_memory_count_for(factory, ids["mission"]) == 1

    async with factory() as session:
        item = await session.scalar(select(ConsciousMemory).where(ConsciousMemory.source_id == ids["mission"]))
        assert item.source_type == "mission"
        assert item.metadata_json["trigger"] == "mission_manifested"
        assert len(item.embedding) == 8

    # Idempotent repeat — manifestation already exists, no second consolidation.
    async with factory() as session:
        _, created_again = await ManifestationService(ManifestationRepository(session)).manifest(
            ids["mission"], correlation_id=str(uuid.uuid4()), actor_id="test", actor_role="worker",
        )
    assert created_again is False
    assert await _conscious_memory_count_for(factory, ids["mission"]) == 1


@pytest.mark.asyncio
async def test_explicit_trigger_is_independent_of_mission_lifecycle(consolidation_db):  # noqa: F811
    """Trigger (ii): an explicit Creator decision consolidates regardless of
    mission state — it is not gated by the mission tail at all."""
    from app.core.domain import Actor

    factory, ids = consolidation_db
    async with factory() as session:
        service = ConsciousMemoryService(ConsciousMemoryRepository(session))
        item = await service.consolidate_explicit(
            Actor(id=ids["creator"], role="creator"),
            source_type="creator_decision",
            source_id=ids["mission"],
            content="Explicitly worth remembering, independent of manifestation.",
            correlation_id=str(uuid.uuid4()),
        )
    assert item.metadata_json["trigger"] == "explicit_creator_decision"
    assert await _conscious_memory_count_for(factory, ids["mission"]) == 1
