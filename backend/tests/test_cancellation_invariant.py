from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain import Actor, InceptionStatus, MissionStatus
from app.kernel.orchestrator import claim_next_ready_task
from app.repositories.domain import DomainRepository
from app.services.domain import LivingCoreService


async def _mission_with_ready_task(session: AsyncSession, *, status: MissionStatus):
    creator_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    actor = Actor(creator_id, "creator")
    service = LivingCoreService(DomainRepository(session))

    from app.models.entities import Creator

    session.add(Creator(id=creator_id, username=f"creator-{creator_id}", password_hash="unused", is_active=True))
    await session.commit()
    conversation = await service.create_conversation(actor, "Cancellation invariant", correlation_id)
    message = await service.add_message(actor, conversation.id, "test", {}, correlation_id)
    inception = await service.create_inception(actor, conversation.id, message.id, "Invariant", "Invariant", correlation_id)
    await service.transition_inception(actor, inception.id, InceptionStatus.AWAITING_CREATOR_DECISION, correlation_id)
    await service.transition_inception(actor, inception.id, InceptionStatus.APPROVED, correlation_id)
    universe = await service.create_universe(actor, f"u-{creator_id}", "Invariant", correlation_id)
    await service.set_universe_active(actor, universe.id, True, correlation_id)
    await service.create_agent(actor, f"a-{creator_id}", "Invariant", universe.id, {}, correlation_id)
    mission = await service.create_mission(actor, inception.id, "Invariant", "Invariant", correlation_id)
    await service.transition_mission(
        actor,
        mission.id,
        MissionStatus.PLANNED,
        correlation_id,
        {
            "strategy": "single step",
            "steps": [{
                "step_key": "only",
                "title": "Only",
                "description": "Only",
                "universe": f"u-{creator_id}",
                "position": 1,
                "depends_on": [],
                "completion_criteria": {},
            }],
            "completion_criteria": {"all_tasks_succeeded": True},
        },
    )
    await service.transition_mission(actor, mission.id, MissionStatus.VALIDATED, correlation_id)
    await service.transition_mission(actor, mission.id, MissionStatus.AUTHORIZED, correlation_id)
    await service.transition_mission(actor, mission.id, MissionStatus.DISTRIBUTED, correlation_id)
    if status == MissionStatus.EXECUTING:
        await service.transition_mission(actor, mission.id, MissionStatus.EXECUTING, correlation_id)
    elif status == MissionStatus.CANCELLED:
        await service.transition_mission(actor, mission.id, MissionStatus.CANCELLED, correlation_id)
    await session.commit()
    return mission


@pytest.mark.asyncio
async def test_cancelled_mission_never_claims_ready_task(db_session: AsyncSession):
    mission = await _mission_with_ready_task(db_session, status=MissionStatus.CANCELLED)

    claimed = await claim_next_ready_task(db_session, mission.id)

    assert claimed is None


@pytest.mark.asyncio
async def test_non_executing_mission_never_claims_ready_task(db_session: AsyncSession):
    mission = await _mission_with_ready_task(db_session, status=MissionStatus.DISTRIBUTED)

    claimed = await claim_next_ready_task(db_session, mission.id)

    assert claimed is None
