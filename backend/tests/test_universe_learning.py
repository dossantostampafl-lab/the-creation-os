from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.entities import Universe
from app.repositories.domain import DomainRepository
from app.services.opportunity import record_learning_episode

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_learning_updates_preferences_without_persisting_authority_fields() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    universe_id = str(uuid.uuid4())
    async with factory() as session:
        session.add(Universe(id=universe_id, code=f"u-{universe_id[:8]}", name="Learning", active=True))
        await session.commit()

    async with factory() as session:
        repo = DomainRepository(session)
        first = await record_learning_episode(
            repo,
            universe_id=universe_id,
            source="provider-result",
            strategy={
                "provider": "exa",
                "sensor": "web.search",
                "detector": "demand_gap",
                "allowed_capabilities": ["anything"],
                "risk_ceiling": 999,
            },
            outcome={"success": True, "reward": 0.5, "authorization": {"expand": True}},
            correlation_id=str(uuid.uuid4()),
        )
        second = await record_learning_episode(
            repo,
            universe_id=universe_id,
            source="provider-result",
            strategy={"provider": "exa", "sensor": "web.search", "detector": "demand_gap"},
            outcome={"success": False},
            correlation_id=str(uuid.uuid4()),
        )
        assert first.id == second.id
        value = second.value_json
        assert value["provider_preferences"]["exa"] == pytest.approx(-0.5)
        assert value["sensor_preferences"]["web.search"] == pytest.approx(-0.5)
        assert value["detector_weights"]["demand_gap"] == pytest.approx(-0.5)
        assert len(value["episodes"]) == 2
        assert "allowed_capabilities" not in value["episodes"][0]["strategy"]
        assert "risk_ceiling" not in value["episodes"][0]["strategy"]
        assert "authorization" not in value["episodes"][0]["outcome"]

    await engine.dispose()
