from __future__ import annotations

import asyncio
import importlib
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.entities import Creator, Mission, Universe
from app.models.opportunity import Opportunity, OpportunityLease, OpportunityThesis
from app.repositories.domain import DomainRepository

pytestmark = pytest.mark.integration


def _service():
    return importlib.import_module("app.services.opportunity")


async def _seed_competition(factory) -> dict[str, str]:
    creator_id = str(uuid.uuid4())
    universe_a = str(uuid.uuid4())
    universe_b = str(uuid.uuid4())
    opportunity_id = str(uuid.uuid4())
    thesis_a = str(uuid.uuid4())
    thesis_b = str(uuid.uuid4())

    async with factory() as session:
        session.add(Creator(id=creator_id, username=f"creator-{creator_id[:8]}", password_hash="x", is_active=True))
        session.add_all([
            Universe(id=universe_a, code=f"u-{universe_a[:8]}", name="Lease A", active=True),
            Universe(id=universe_b, code=f"u-{universe_b[:8]}", name="Lease B", active=True),
        ])
        await session.commit()

        session.add(Opportunity(
            id=opportunity_id,
            creator_id=creator_id,
            fingerprint=f"fp-{opportunity_id}",
            sector="software",
            problem_or_gap="lease race",
            capture_mechanism="service",
            evidence_refs_json=["test:evidence"],
            first_discovered_by_universe_id=universe_a,
            time_window_json={},
            status="DETECTED",
        ))
        await session.commit()

        session.add_all([
            OpportunityThesis(
                id=thesis_a,
                opportunity_id=opportunity_id,
                universe_id=universe_a,
                proposed_value="A",
                target_payer="payer",
                capture_path="service",
                estimated_cost_json={},
                expected_value_json={},
                max_downside_json={},
                confidence=0.7,
                falsification_conditions_json=["invalid"],
                evidence_refs_json=["test:a"],
                status="PROPOSED",
            ),
            OpportunityThesis(
                id=thesis_b,
                opportunity_id=opportunity_id,
                universe_id=universe_b,
                proposed_value="B",
                target_payer="payer",
                capture_path="service",
                estimated_cost_json={},
                expected_value_json={},
                max_downside_json={},
                confidence=0.8,
                falsification_conditions_json=["invalid"],
                evidence_refs_json=["test:b"],
                status="PROPOSED",
            ),
        ])
        await session.commit()

    return {
        "creator_id": creator_id,
        "universe_a": universe_a,
        "universe_b": universe_b,
        "opportunity_id": opportunity_id,
        "thesis_a": thesis_a,
        "thesis_b": thesis_b,
    }


@pytest.mark.asyncio
async def test_two_concurrent_executive_contenders_yield_exactly_one_winner() -> None:
    service = _service()
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids = await _seed_competition(factory)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    async def contend(universe_id: str, thesis_id: str) -> str | None:
        async with factory() as session:
            repository = DomainRepository(session)
            try:
                lease = await service.acquire_executive_lease(
                    repository,
                    opportunity_id=ids["opportunity_id"],
                    thesis_id=thesis_id,
                    universe_id=universe_id,
                    expires_at=expires_at,
                    correlation_id=str(uuid.uuid4()),
                )
            except service.LeaseConflictError:
                return None
            return lease.id

    winners = await asyncio.gather(
        contend(ids["universe_a"], ids["thesis_a"]),
        contend(ids["universe_b"], ids["thesis_b"]),
    )
    assert sum(item is not None for item in winners) == 1

    async with factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(OpportunityLease).where(
                OpportunityLease.opportunity_id == ids["opportunity_id"],
                OpportunityLease.lease_type == "EXECUTIVE",
                OpportunityLease.status == "ACTIVE",
            )
        )
        assert count == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_research_leases_can_coexist_and_release_is_explicit() -> None:
    service = _service()
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids = await _seed_competition(factory)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    async with factory() as session:
        repository = DomainRepository(session)
        first = await service.acquire_research_lease(
            repository,
            opportunity_id=ids["opportunity_id"],
            thesis_id=ids["thesis_a"],
            universe_id=ids["universe_a"],
            expires_at=expires_at,
            correlation_id=str(uuid.uuid4()),
        )
        second = await service.acquire_research_lease(
            repository,
            opportunity_id=ids["opportunity_id"],
            thesis_id=ids["thesis_b"],
            universe_id=ids["universe_b"],
            expires_at=expires_at,
            correlation_id=str(uuid.uuid4()),
        )
        assert first.id != second.id
        assert first.status == second.status == "ACTIVE"

        released = await service.release_lease(
            repository,
            lease_id=first.id,
            universe_id=ids["universe_a"],
            correlation_id=str(uuid.uuid4()),
        )
        assert released.status == "RELEASED"
        assert released.released_at is not None
        assert second.status == "ACTIVE"

    await engine.dispose()


@pytest.mark.asyncio
async def test_expired_executive_lease_can_be_replaced() -> None:
    service = _service()
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids = await _seed_competition(factory)
    old_lease_id = str(uuid.uuid4())

    async with factory() as session:
        session.add(OpportunityLease(
            id=old_lease_id,
            opportunity_id=ids["opportunity_id"],
            thesis_id=ids["thesis_a"],
            universe_id=ids["universe_a"],
            lease_type="EXECUTIVE",
            status="ACTIVE",
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        ))
        await session.commit()

    async with factory() as session:
        repository = DomainRepository(session)
        replacement = await service.acquire_executive_lease(
            repository,
            opportunity_id=ids["opportunity_id"],
            thesis_id=ids["thesis_b"],
            universe_id=ids["universe_b"],
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            correlation_id=str(uuid.uuid4()),
        )
        assert replacement.id != old_lease_id
        assert replacement.status == "ACTIVE"

    async with factory() as session:
        old = await session.get(OpportunityLease, old_lease_id)
        assert old is not None
        assert old.status == "EXPIRED"
        assert old.released_at is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_selecting_thesis_does_not_create_or_authorize_a_mission() -> None:
    service = _service()
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids = await _seed_competition(factory)

    async with factory() as session:
        repository = DomainRepository(session)
        selected = await service.select_thesis(
            repository,
            opportunity_id=ids["opportunity_id"],
            thesis_id=ids["thesis_b"],
            correlation_id=str(uuid.uuid4()),
        )
        assert selected.status == "SELECTED"

        mission_count = await session.scalar(
            select(func.count()).select_from(Mission).where(Mission.opportunity_id == ids["opportunity_id"])
        )
        assert mission_count == 0

    await engine.dispose()
