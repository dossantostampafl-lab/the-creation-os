from __future__ import annotations

import pytest
from sqlalchemy import select
from test_knowledge import knowledge_db  # noqa: F401

from app.autonomy.perception import PerceptionObservation


class FakePerceptionFabric:
    async def observe(
        self,
        *,
        creator_id: str,
        universe_code: str,
        preferred_sensors: list[str],
        query: str,
        explore: bool,
    ) -> list[PerceptionObservation]:
        return [
            PerceptionObservation(
                sensor="web.search",
                capability="web",
                action="search",
                data={
                    "provider": "test-web",
                    "items": [{"title": "External signal", "content": "Recurring paid demand"}],
                },
            )
        ]


@pytest.mark.asyncio
async def test_discovery_worker_turns_multisensor_observation_into_opportunity_without_mission(
    knowledge_db,  # noqa: F811
) -> None:
    from app.autonomy.discovery import DiscoveryWorker
    from app.models.entities import Agent, Mission, Universe
    from app.models.opportunity import Opportunity

    factory, creator_id, _ = knowledge_db
    async with factory() as session:
        universe = await session.scalar(select(Universe).where(Universe.code == "engineering"))
        assert universe is not None
        universe_id = universe.id

        agent = await session.scalar(
            select(Agent)
            .where(Agent.universe_id == universe_id, Agent.active.is_(True))
            .limit(1)
        )
        if agent is None:
            agent = Agent(
                code="engineering-agent-perception-test",
                name="Engineering Perception Test Agent",
                universe_id=universe_id,
                active=True,
                capabilities_json={},
            )
            session.add(agent)

        agent.capabilities_json = {
            "preferred_sensors": ["web.search"],
            "exploration_strategy": {"mode": "cross_sector"},
        }
        await session.commit()

    worker = DiscoveryWorker(factory, perception=FakePerceptionFabric())
    report = await worker.run_once(creator_id)

    assert report["sensor_observations"] == 1
    async with factory() as session:
        rows = list((await session.scalars(select(Opportunity).where(
            Opportunity.creator_id == creator_id,
            Opportunity.first_discovered_by_universe_id == universe_id,
        ))).all())
        assert len(rows) == 1
        assert any(ref.startswith("sensor:web.search:") for ref in rows[0].evidence_refs_json)
        assert not list((await session.scalars(select(Mission))).all())
