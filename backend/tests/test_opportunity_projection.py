from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.economy import EconomicLedgerEntry
from app.models.entities import Creator, Universe
from app.models.opportunity import Opportunity
from app.projections.opportunity import build_creator_opportunity_projection

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_opportunity_projection_is_creator_scoped() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    creator_a = str(uuid.uuid4())
    creator_b = str(uuid.uuid4())
    universe_id = str(uuid.uuid4())

    async with factory() as session:
        session.add_all([
            Creator(id=creator_a, username=f"creator-{creator_a[:8]}", password_hash="x", is_active=True),
            Creator(id=creator_b, username=f"creator-{creator_b[:8]}", password_hash="x", is_active=True),
            Universe(id=universe_id, code=f"u-{universe_id[:8]}", name="Projection", active=True),
        ])
        await session.flush()
        session.add_all([
            Opportunity(
                creator_id=creator_a,
                fingerprint=f"fp-{creator_a}",
                sector="software",
                problem_or_gap="gap a",
                capture_mechanism="service",
                evidence_refs_json=["a"],
                first_discovered_by_universe_id=universe_id,
                time_window_json={},
                status="SELECTED",
            ),
            Opportunity(
                creator_id=creator_b,
                fingerprint=f"fp-{creator_b}",
                sector="software",
                problem_or_gap="gap b",
                capture_mechanism="service",
                evidence_refs_json=["b"],
                first_discovered_by_universe_id=universe_id,
                time_window_json={},
                status="DETECTED",
            ),
            EconomicLedgerEntry(
                creator_id=creator_a,
                universe_id=universe_id,
                mission_id=None,
                opportunity_id=None,
                entry_type="GENESIS",
                amount=Decimal("10"),
                currency="BRL",
                status="SETTLED",
                external_reference=f"genesis:{creator_a}",
                metadata_json={"mode": "real"},
            ),
            EconomicLedgerEntry(
                creator_id=creator_b,
                universe_id=universe_id,
                mission_id=None,
                opportunity_id=None,
                entry_type="GENESIS",
                amount=Decimal("100"),
                currency="BRL",
                status="SETTLED",
                external_reference=f"genesis:{creator_b}",
                metadata_json={"mode": "real"},
            ),
        ])
        await session.commit()

    async with factory() as session:
        projection = await build_creator_opportunity_projection(
            session, creator_id=creator_a, currency="BRL"
        )
        assert projection["opportunities"]["total"] == 1
        assert projection["opportunities"]["by_status"] == {"SELECTED": 1
        }
        assert len(projection["universe_economy"]) == 1
        assert Decimal(projection["universe_economy"][0]["nav"]) == Decimal("10")

    await engine.dispose()
