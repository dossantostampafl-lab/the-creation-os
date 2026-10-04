from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from stf_database import stf_db  # noqa: F401

from app.models.entities import Agent, Creator, Universe
from app.models.security_task_force import StfRun
from app.security_task_force.contracts import RiskClass
from app.security_task_force.training import (
    ADVANCED_CAMPAIGN_ID,
    RANGE_ENVIRONMENT_ID,
    TRAINING_AGENT_SPECS,
    AutomaticRangeTraining,
    TrainingHistory,
    build_training_actions,
    compile_training_contract,
    ensure_training_agents,
    select_next_training_agent,
)


def test_training_roster_has_exactly_ten_distinct_security_specialists() -> None:
    assert len(TRAINING_AGENT_SPECS) == 10
    assert len({item.code for item in TRAINING_AGENT_SPECS}) == 10
    assert len({item.specialty for item in TRAINING_AGENT_SPECS}) == 10
    assert all(item.code.startswith("stf-") for item in TRAINING_AGENT_SPECS)


def test_training_contract_is_range_only_and_never_self_escalates() -> None:
    spec = TRAINING_AGENT_SPECS[0]
    compiled = compile_training_contract("creator-1", spec)

    assert compiled.status == "COMPILED"
    assert compiled.contract is not None
    contract = compiled.contract
    assert contract.authorized_environments == [RANGE_ENVIRONMENT_ID]
    assert contract.authorized_targets == [ADVANCED_CAMPAIGN_ID]
    assert contract.excluded_targets == ["real:*"]
    assert contract.risk_ceiling is RiskClass.R2
    assert contract.allowed_action_classes == ["range.training"]


def test_training_plan_drives_the_advanced_campaign_to_completion() -> None:
    spec = TRAINING_AGENT_SPECS[3]
    compiled = compile_training_contract("creator-1", spec)
    assert compiled.contract is not None

    actions = build_training_actions(compiled.contract, spec, cycle=7)

    assert [item.capability for item in actions] == [
        "range.campaign.start",
        "range.campaign.advance",
        "range.campaign.advance",
        "range.campaign.advance",
        "range.campaign.verify",
    ]
    assert all(item.environment_id == RANGE_ENVIRONMENT_ID for item in actions)
    assert all(item.target_id == ADVANCED_CAMPAIGN_ID for item in actions)
    assert all(item.action_class == "range.training" for item in actions)
    assert all(item.actor == f"agent:{spec.code}" for item in actions)
    assert len({item.action_id for item in actions}) == len(actions)
    assert len({item.idempotency_key for item in actions}) == len(actions)
    assert max(item.risk_class.rank for item in actions) <= RiskClass.R2.rank


def test_round_robin_prefers_untrained_then_least_recent_agent() -> None:
    now = datetime(2026, 10, 3, tzinfo=timezone.utc)
    specs = TRAINING_AGENT_SPECS[:3]

    first = select_next_training_agent(
        specs,
        {
            specs[0].code: TrainingHistory(cycles=2, last_started_at=now),
            specs[1].code: TrainingHistory(cycles=1, last_started_at=now),
        },
    )
    assert first.code == specs[2].code

    second = select_next_training_agent(
        specs,
        {
            specs[0].code: TrainingHistory(cycles=2, last_started_at=now),
            specs[1].code: TrainingHistory(cycles=1, last_started_at=now),
            specs[2].code: TrainingHistory(cycles=1, last_started_at=datetime(2026, 10, 2, tzinfo=timezone.utc)),
        },
    )
    assert second.code == specs[2].code


@pytest.mark.integration
@pytest.mark.asyncio
async def test_training_agents_are_seeded_idempotently_under_security_universe(stf_db) -> None:  # noqa: F811
    _, factory = stf_db
    creator_id = str(uuid.uuid4())
    async with factory() as session:
        security = await session.scalar(select(Universe).where(Universe.code == "security"))
        if security is None:
            security = Universe(id=str(uuid.uuid4()), code="security", name="Segurança", active=True)
            session.add(security)
        session.add(Creator(id=creator_id, username="creator-training", password_hash="unused", is_active=True))
        await session.commit()

    async with factory() as session:
        first = await ensure_training_agents(session)
        await session.commit()
    async with factory() as session:
        second = await ensure_training_agents(session)
        await session.commit()
        rows = list(
            (
                await session.scalars(
                    select(Agent).where(Agent.code.in_([item.code for item in TRAINING_AGENT_SPECS]))
                )
            ).all()
        )

    assert len(first) == len(second) == len(rows) == 10
    assert {item.code for item in rows} == {item.code for item in TRAINING_AGENT_SPECS}
    assert all(item.active for item in rows)
    assert all(item.capabilities_json["training_profile"] == "stf-cyber-range-v1" for item in rows)
    assert all(item.capabilities_json["real_target_authority"] is False for item in rows)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auto_training_queues_one_serialized_range_run_and_does_not_duplicate_active_run(stf_db) -> None:  # noqa: F811
    _, factory = stf_db
    creator_id = str(uuid.uuid4())
    async with factory() as session:
        security = await session.scalar(select(Universe).where(Universe.code == "security"))
        if security is None:
            session.add(Universe(id=str(uuid.uuid4()), code="security", name="Segurança", active=True))
        session.add(Creator(id=creator_id, username="creator-autotrain", password_hash="unused", is_active=True))
        await session.commit()

    coordinator = AutomaticRangeTraining(factory)
    first = await coordinator.run_once(creator_id)
    second = await coordinator.run_once(creator_id)

    assert first["status"] == "queued"
    assert second["status"] == "busy"
    async with factory() as session:
        runs = list((await session.scalars(select(StfRun).where(StfRun.creator_id == creator_id))).all())
        agent_count = int(
            await session.scalar(
                select(func.count()).select_from(Agent).where(
                    Agent.code.in_([item.code for item in TRAINING_AGENT_SPECS])
                )
            )
            or 0
        )

    assert len(runs) == 1
    assert agent_count == 10
    assert len(runs[0].plan_json) == 5
    assert runs[0].plan_json[0]["capability"] == "range.campaign.start"
    assert runs[0].plan_json[-1]["capability"] == "range.campaign.verify"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_training_seed_does_not_undo_a_creator_pause(stf_db) -> None:  # noqa: F811
    _, factory = stf_db
    async with factory() as session:
        if await session.scalar(select(Universe).where(Universe.code == "security")) is None:
            session.add(Universe(id=str(uuid.uuid4()), code="security", name="Segurança", active=True))
            await session.flush()
        agents = await ensure_training_agents(session)
        agent = agents[0]
        agent.active = False
        await session.commit()
    try:
        async with factory() as session:
            await ensure_training_agents(session)
            await session.commit()
        async with factory() as session:
            paused = await session.scalar(select(Agent).where(Agent.id == agent.id))
            assert paused is not None and paused.active is False
    finally:
        async with factory() as session:
            restored = await session.get(Agent, agent.id)
            if restored is not None:
                restored.active = True
            await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_manual_training_selects_agent_and_serializes_competing_requests(stf_db) -> None:  # noqa: F811
    import asyncio

    _, factory = stf_db
    creator_id = str(uuid.uuid4())
    async with factory() as session:
        if await session.scalar(select(Universe).where(Universe.code == "security")) is None:
            session.add(Universe(id=str(uuid.uuid4()), code="security", name="Segurança", active=True))
        session.add(Creator(id=creator_id, username="creator-manual-train", password_hash="unused", is_active=True))
        await session.commit()
    coordinator = AutomaticRangeTraining(factory)
    selected = TRAINING_AGENT_SPECS[4].code
    results = await asyncio.gather(
        coordinator.run_once(creator_id, agent_code=selected),
        coordinator.run_once(creator_id, agent_code=TRAINING_AGENT_SPECS[5].code),
    )
    assert sorted(str(result["status"]) for result in results) == ["busy", "queued"]
    queued = next(result for result in results if result["status"] == "queued")
    assert queued["agent_code"] in {selected, TRAINING_AGENT_SPECS[5].code}
    async with factory() as session:
        count = await session.scalar(select(func.count()).select_from(StfRun).where(StfRun.creator_id == creator_id))
        assert count == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_paused_roster_never_queues_and_manual_paused_agent_is_rejected(stf_db) -> None:  # noqa: F811
    _, factory = stf_db
    creator_id = str(uuid.uuid4())
    async with factory() as session:
        if await session.scalar(select(Universe).where(Universe.code == "security")) is None:
            session.add(Universe(id=str(uuid.uuid4()), code="security", name="Segurança", active=True))
            await session.flush()
        agents = await ensure_training_agents(session)
        original = {agent.id: agent.active for agent in agents}
        for agent in agents:
            agent.active = False
        session.add(Creator(id=creator_id, username="creator-paused-train", password_hash="unused", is_active=True))
        await session.commit()
    try:
        coordinator = AutomaticRangeTraining(factory)
        assert await coordinator.run_once(creator_id) == {"status": "paused", "agents_ready": 0}
        with pytest.raises(ValueError, match="paused"):
            await coordinator.run_once(creator_id, agent_code=TRAINING_AGENT_SPECS[0].code)
        with pytest.raises(ValueError, match="Unknown"):
            await coordinator.run_once(creator_id, agent_code="external-target")
        async with factory() as session:
            assert not (await session.scalars(select(StfRun).where(StfRun.creator_id == creator_id))).all()
    finally:
        async with factory() as session:
            for agent in (await session.scalars(select(Agent).where(Agent.id.in_(original)))).all():
                agent.active = original[agent.id]
            await session.commit()
