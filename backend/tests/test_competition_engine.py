from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.entities import Creator, Universe
from app.models.opportunity import Opportunity, OpportunityLease, OpportunityThesis
from app.repositories.domain import DomainRepository
from app.services.opportunity import resolve_competition

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_resolve_competition_selects_highest_supplied_score_and_awards_one_executive_lease() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    creator_id = str(uuid.uuid4())
    opportunity_id = str(uuid.uuid4())
    universe_a = str(uuid.uuid4())
    universe_b = str(uuid.uuid4())
    thesis_a = str(uuid.uuid4())
    thesis_b = str(uuid.uuid4())

    async with factory() as session:
        session.add_all([
            Creator(id=creator_id, username=f"creator-{creator_id[:8]}", password_hash="x", is_active=True),
            Universe(id=universe_a, code=f"u-{universe_a[:8]}", name="A", active=True),
            Universe(id=universe_b, code=f"u-{universe_b[:8]}", name="B", active=True),
        ])
        await session.flush()
        session.add(Opportunity(
            id=opportunity_id,
            creator_id=creator_id,
            fingerprint=f"fp-{opportunity_id}",
            sector="software",
            problem_or_gap="verified gap",
            capture_mechanism="bounded service",
            evidence_refs_json=["test:evidence"],
            first_discovered_by_universe_id=universe_a,
            time_window_json={},
            status="DETECTED",
        ))
        await session.flush()
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
                confidence=0.8,
                falsification_conditions_json=["invalidated"],
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
                confidence=0.7,
                falsification_conditions_json=["invalidated"],
                evidence_refs_json=["test:b"],
                status="PROPOSED",
            ),
        ])
        await session.commit()

    async with factory() as session:
        winner, lease = await resolve_competition(
            DomainRepository(session),
            opportunity_id=opportunity_id,
            scores={thesis_a: 0.25, thesis_b: 0.90},
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            correlation_id=str(uuid.uuid4()),
        )
        assert winner.id == thesis_b
        assert winner.status == "SELECTED"
        assert lease.thesis_id == thesis_b
        assert lease.universe_id == universe_b
        assert lease.lease_type == "EXECUTIVE"
        assert lease.status == "ACTIVE"

    async with factory() as session:
        selected = list((await session.scalars(select(OpportunityThesis).where(
            OpportunityThesis.opportunity_id == opportunity_id,
            OpportunityThesis.status == "SELECTED",
        ))).all())
        active = await session.scalar(select(func.count()).select_from(OpportunityLease).where(
            OpportunityLease.opportunity_id == opportunity_id,
            OpportunityLease.lease_type == "EXECUTIVE",
            OpportunityLease.status == "ACTIVE",
        ))
        assert [item.id for item in selected] == [thesis_b]
        assert active == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_resolve_competition_rejects_unknown_or_non_finite_scores() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        with pytest.raises(ValueError):
            await resolve_competition(
                DomainRepository(session),
                opportunity_id=str(uuid.uuid4()),
                scores={},
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                correlation_id=str(uuid.uuid4()),
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_resolve_competition_tie_break_is_deterministic() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    creator_id = str(uuid.uuid4())
    opportunity_id = str(uuid.uuid4())
    universe_a = str(uuid.uuid4())
    universe_b = str(uuid.uuid4())
    thesis_a = str(uuid.uuid4())
    thesis_b = str(uuid.uuid4())

    async with factory() as session:
        session.add_all([
            Creator(id=creator_id, username=f"creator-{creator_id[:8]}", password_hash="x", is_active=True),
            Universe(id=universe_a, code=f"u-{universe_a[:8]}", name="A", active=True),
            Universe(id=universe_b, code=f"u-{universe_b[:8]}", name="B", active=True),
        ])
        await session.flush()
        session.add(Opportunity(
            id=opportunity_id,
            creator_id=creator_id,
            fingerprint=f"fp-{opportunity_id}",
            sector="software",
            problem_or_gap="tie",
            capture_mechanism="service",
            evidence_refs_json=["test:evidence"],
            first_discovered_by_universe_id=universe_a,
            time_window_json={},
            status="DETECTED",
        ))
        await session.flush()
        session.add_all([
            OpportunityThesis(
                id=thesis_a, opportunity_id=opportunity_id, universe_id=universe_a,
                proposed_value="A", target_payer="payer", capture_path="service",
                estimated_cost_json={}, expected_value_json={}, max_downside_json={},
                confidence=0.6, falsification_conditions_json=["x"],
                evidence_refs_json=["a"], status="PROPOSED",
            ),
            OpportunityThesis(
                id=thesis_b, opportunity_id=opportunity_id, universe_id=universe_b,
                proposed_value="B", target_payer="payer", capture_path="service",
                estimated_cost_json={}, expected_value_json={}, max_downside_json={},
                confidence=0.9, falsification_conditions_json=["x"],
                evidence_refs_json=["b"], status="PROPOSED",
            ),
        ])
        await session.commit()

    async with factory() as session:
        winner, _ = await resolve_competition(
            DomainRepository(session),
            opportunity_id=opportunity_id,
            scores={thesis_a: 0.5, thesis_b: 0.5},
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            correlation_id=str(uuid.uuid4()),
        )
        assert winner.id == thesis_b

    await engine.dispose()
