from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.economy import EconomicLedgerEntry
from app.models.entities import Creator, Mission, Universe
from app.models.opportunity import Opportunity, OpportunityLease, OpportunityThesis
from app.repositories.domain import DomainRepository
from app.services.economy import (
    EconomicPolicyError,
    append_ledger_entry,
    ensure_genesis_allocation,
    reserve_for_capability,
)
from app.services.opportunity import create_mission_from_opportunity, create_or_get_opportunity

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_opportunity_dedupe_race_yields_one_row() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    creator_id = str(uuid.uuid4())
    universe_id = str(uuid.uuid4())
    async with factory() as session:
        session.add_all([
            Creator(id=creator_id, username=f"creator-{creator_id[:8]}", password_hash="x", is_active=True),
            Universe(id=universe_id, code=f"u-{universe_id[:8]}", name="Dedupe Race", active=True),
        ])
        await session.commit()

    async def contend(evidence: str):
        async with factory() as session:
            return await create_or_get_opportunity(
                DomainRepository(session),
                creator_id=creator_id,
                discovered_by_universe_id=universe_id,
                sector="software",
                problem_or_gap="same verified gap",
                capture_mechanism="subscription",
                evidence_refs=[evidence],
                time_window={"kind": "test"},
                correlation_id=str(uuid.uuid4()),
            )

    left, right = await asyncio.gather(contend("test:left"), contend("test:right"))
    assert left.id == right.id
    async with factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(Opportunity).where(Opportunity.creator_id == creator_id)
        )
        assert count == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_opportunity_mission_creation_race_yields_one_row() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    creator_id = str(uuid.uuid4())
    universe_id = str(uuid.uuid4())
    opportunity_id = str(uuid.uuid4())
    thesis_id = str(uuid.uuid4())
    lease_id = str(uuid.uuid4())

    async with factory() as session:
        session.add_all([
            Creator(id=creator_id, username=f"creator-{creator_id[:8]}", password_hash="x", is_active=True),
            Universe(id=universe_id, code=f"u-{universe_id[:8]}", name="Mission Race", active=True),
        ])
        await session.flush()
        session.add(Opportunity(
            id=opportunity_id,
            creator_id=creator_id,
            fingerprint=f"fp-{opportunity_id}",
            sector="software",
            problem_or_gap="mission race",
            capture_mechanism="service",
            evidence_refs_json=["test:evidence"],
            first_discovered_by_universe_id=universe_id,
            time_window_json={},
            status="SELECTED",
        ))
        await session.flush()
        session.add(OpportunityThesis(
            id=thesis_id,
            opportunity_id=opportunity_id,
            universe_id=universe_id,
            proposed_value="capture",
            target_payer="payer",
            capture_path="service",
            estimated_cost_json={},
            expected_value_json={},
            max_downside_json={},
            confidence=0.8,
            falsification_conditions_json=["invalidated"],
            evidence_refs_json=["test:evidence"],
            status="SELECTED",
        ))
        await session.flush()
        session.add(OpportunityLease(
            id=lease_id,
            opportunity_id=opportunity_id,
            thesis_id=thesis_id,
            universe_id=universe_id,
            lease_type="EXECUTIVE",
            status="ACTIVE",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        ))
        await session.commit()

    async def contend():
        async with factory() as session:
            return await create_mission_from_opportunity(
                DomainRepository(session),
                creator_id=creator_id,
                opportunity_id=opportunity_id,
                thesis_id=thesis_id,
                executive_lease_id=lease_id,
                title="race mission",
                objective="capture value",
                authorization={},
                correlation_id=str(uuid.uuid4()),
            )

    first, second = await asyncio.gather(contend(), contend())
    assert first.id == second.id
    async with factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(Mission).where(Mission.opportunity_id == opportunity_id)
        )
        assert count == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_economic_reservation_race_respects_database_serialized_exposure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    creator_id = str(uuid.uuid4())
    universe_id = str(uuid.uuid4())
    opportunity_id = str(uuid.uuid4())
    mission_id = str(uuid.uuid4())

    async with factory() as session:
        session.add_all([
            Creator(id=creator_id, username=f"creator-{creator_id[:8]}", password_hash="x", is_active=True),
            Universe(id=universe_id, code=f"u-{universe_id[:8]}", name="Reserve Race", active=True),
        ])
        await session.flush()
        session.add(Opportunity(
            id=opportunity_id,
            creator_id=creator_id,
            fingerprint=f"fp-{opportunity_id}",
            sector="software",
            problem_or_gap="reserve race",
            capture_mechanism="service",
            evidence_refs_json=["test:evidence"],
            first_discovered_by_universe_id=universe_id,
            time_window_json={},
            status="SELECTED",
        ))
        await session.flush()
        session.add(Mission(
            id=mission_id,
            inception_id=None,
            opportunity_id=opportunity_id,
            creator_id=creator_id,
            title="reserve",
            objective="bounded reservation",
        ))
        await session.commit()

    monkeypatch.setattr(settings, "real_economic_mode_enabled", True)
    monkeypatch.setattr(settings, "economic_max_exposure_ratio", 0.10)
    monkeypatch.setattr(settings, "economic_max_risk_per_action_ratio", 0.10)

    async with factory() as session:
        await ensure_genesis_allocation(
            DomainRepository(session),
            creator_id=creator_id,
            universe_id=universe_id,
            correlation_id=str(uuid.uuid4()),
        )

    async def reserve(reference: str):
        async with factory() as session:
            try:
                return await reserve_for_capability(
                    DomainRepository(session),
                    creator_id=creator_id,
                    universe_id=universe_id,
                    mission_id=mission_id,
                    opportunity_id=opportunity_id,
                    amount=Decimal("1"),
                    currency="BRL",
                    external_reference=reference,
                    metadata={},
                    correlation_id=str(uuid.uuid4()),
                )
            except EconomicPolicyError as exc:
                return exc

    results = await asyncio.gather(reserve("race-a"), reserve("race-b"))
    assert sum(isinstance(item, EconomicPolicyError) for item in results) == 1
    async with factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(EconomicLedgerEntry).where(
                EconomicLedgerEntry.creator_id == creator_id,
                EconomicLedgerEntry.entry_type == "RESERVE",
            )
        )
        assert count == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_settlement_and_reconciliation_races_are_idempotent() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    creator_id = str(uuid.uuid4())
    universe_id = str(uuid.uuid4())
    async with factory() as session:
        session.add_all([
            Creator(id=creator_id, username=f"creator-{creator_id[:8]}", password_hash="x", is_active=True),
            Universe(id=universe_id, code=f"u-{universe_id[:8]}", name="Settlement Race", active=True),
        ])
        await session.commit()

    async def append(kind: str):
        async with factory() as session:
            return await append_ledger_entry(
                DomainRepository(session),
                creator_id=creator_id,
                universe_id=universe_id,
                mission_id=None,
                opportunity_id=None,
                entry_type=kind,
                amount=Decimal("1"),
                currency="BRL",
                status="RECONCILED" if kind == "RECONCILED" else "SETTLED",
                external_reference="effect-race",
                metadata={"mode": "real"},
                correlation_id=str(uuid.uuid4()),
            )

    settlements = await asyncio.gather(append("SETTLE"), append("SETTLE"))
    reconciliations = await asyncio.gather(append("RECONCILED"), append("RECONCILED"))
    assert settlements[0].id == settlements[1].id
    assert reconciliations[0].id == reconciliations[1].id

    async with factory() as session:
        rows = list((await session.scalars(select(EconomicLedgerEntry).where(
            EconomicLedgerEntry.external_reference == "effect-race"
        ))).all())
        assert sorted(item.entry_type for item in rows) == ["RECONCILED", "SETTLE"]
    await engine.dispose()
