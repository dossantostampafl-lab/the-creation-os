from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.domain import InvalidOrigin
from app.models.entities import Creator, Mission, Universe
from app.models.opportunity import Opportunity, OpportunityLease, OpportunityThesis
from app.repositories.domain import DomainRepository
from app.services.domain import NotFoundError
from app.services.opportunity import create_mission_from_opportunity

pytestmark = pytest.mark.integration


async def _seed(factory) -> dict[str, str]:
    ids = {name: str(uuid.uuid4()) for name in ("creator", "other_creator", "universe", "opportunity", "thesis", "lease")}
    async with factory() as session:
        session.add_all([
            Creator(id=ids["creator"], username=f"creator-{ids['creator'][:8]}", password_hash="x", is_active=True),
            Creator(id=ids["other_creator"], username=f"creator-{ids['other_creator'][:8]}", password_hash="x", is_active=True),
            Universe(id=ids["universe"], code=f"u-{ids['universe'][:8]}", name="Opportunity Mission", active=True),
        ])
        await session.flush()
        session.add(Opportunity(
            id=ids["opportunity"], creator_id=ids["creator"], fingerprint=f"fp-{ids['opportunity']}",
            sector="software", problem_or_gap="verified gap", capture_mechanism="service",
            evidence_refs_json=["test:evidence"], first_discovered_by_universe_id=ids["universe"],
            time_window_json={}, status="SELECTED",
        ))
        await session.flush()
        session.add(OpportunityThesis(
            id=ids["thesis"], opportunity_id=ids["opportunity"], universe_id=ids["universe"],
            proposed_value="ship", target_payer="payer", capture_path="service",
            estimated_cost_json={}, expected_value_json={}, max_downside_json={}, confidence=0.8,
            falsification_conditions_json=["invalid"], evidence_refs_json=["test:evidence"], status="SELECTED",
        ))
        await session.flush()
        session.add(OpportunityLease(
            id=ids["lease"], opportunity_id=ids["opportunity"], thesis_id=ids["thesis"],
            universe_id=ids["universe"], lease_type="EXECUTIVE", status="ACTIVE",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        ))
        await session.commit()
    return ids


@pytest.mark.asyncio
async def test_selected_opportunity_with_active_lease_creates_one_mission_idempotently() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids = await _seed(factory)

    async with factory() as session:
        repo = DomainRepository(session)
        mission = await create_mission_from_opportunity(
            repo, creator_id=ids["creator"], opportunity_id=ids["opportunity"], thesis_id=ids["thesis"],
            executive_lease_id=ids["lease"], title="Opportunity mission", objective="capture verified value",
            authorization={"allowed_capabilities": ["web"], "external_effects_allowed": False},
            correlation_id=str(uuid.uuid4()),
        )
        again = await create_mission_from_opportunity(
            repo, creator_id=ids["creator"], opportunity_id=ids["opportunity"], thesis_id=ids["thesis"],
            executive_lease_id=ids["lease"], title="ignored duplicate", objective="ignored duplicate",
            authorization={}, correlation_id=str(uuid.uuid4()),
        )
        assert mission.id == again.id
        assert mission.inception_id is None
        assert mission.opportunity_id == ids["opportunity"]
        assert mission.origin_type == "OPPORTUNITY"
        assert mission.status == "drafted"
        assert mission.authorization_json["allowed_capabilities"] == ["web"]
        count = await session.scalar(
            select(func.count()).select_from(Mission).where(Mission.opportunity_id == ids["opportunity"])
        )
        assert count == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_opportunity_mission_rejects_wrong_creator_and_expired_or_wrong_lease() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids = await _seed(factory)

    async with factory() as session:
        repo = DomainRepository(session)
        with pytest.raises(NotFoundError):
            await create_mission_from_opportunity(
                repo, creator_id=ids["other_creator"], opportunity_id=ids["opportunity"], thesis_id=ids["thesis"],
                executive_lease_id=ids["lease"], title="bad", objective="bad", authorization={},
                correlation_id=str(uuid.uuid4()),
            )

    async with factory() as session:
        lease = await session.get(OpportunityLease, ids["lease"])
        assert lease is not None
        lease.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    async with factory() as session:
        repo = DomainRepository(session)
        with pytest.raises(InvalidOrigin, match="expired"):
            await create_mission_from_opportunity(
                repo, creator_id=ids["creator"], opportunity_id=ids["opportunity"], thesis_id=ids["thesis"],
                executive_lease_id=ids["lease"], title="bad", objective="bad", authorization={},
                correlation_id=str(uuid.uuid4()),
            )
        expired = await session.get(OpportunityLease, ids["lease"])
        assert expired is not None
        assert expired.status == "EXPIRED"
        assert expired.released_at is not None

    await engine.dispose()



@pytest.mark.asyncio
async def test_opportunity_mission_rejects_unselected_thesis_and_lost_lease() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids = await _seed(factory)
    alternate_thesis = str(uuid.uuid4())

    async with factory() as session:
        session.add(OpportunityThesis(
            id=alternate_thesis,
            opportunity_id=ids["opportunity"],
            universe_id=ids["universe"],
            proposed_value="alternate",
            target_payer="payer",
            capture_path="service",
            estimated_cost_json={},
            expected_value_json={},
            max_downside_json={},
            confidence=0.4,
            falsification_conditions_json=["invalid"],
            evidence_refs_json=["test:evidence"],
            status="PROPOSED",
        ))
        await session.commit()

    async with factory() as session:
        repo = DomainRepository(session)
        with pytest.raises(InvalidOrigin, match="selected thesis"):
            await create_mission_from_opportunity(
                repo,
                creator_id=ids["creator"],
                opportunity_id=ids["opportunity"],
                thesis_id=alternate_thesis,
                executive_lease_id=ids["lease"],
                title="bad thesis",
                objective="bad",
                authorization={},
                correlation_id=str(uuid.uuid4()),
            )

    async with factory() as session:
        lease = await session.get(OpportunityLease, ids["lease"])
        assert lease is not None
        lease.status = "RELEASED"
        lease.released_at = datetime.now(timezone.utc)
        await session.commit()

    async with factory() as session:
        repo = DomainRepository(session)
        with pytest.raises(InvalidOrigin, match="active executive lease"):
            await create_mission_from_opportunity(
                repo,
                creator_id=ids["creator"],
                opportunity_id=ids["opportunity"],
                thesis_id=ids["thesis"],
                executive_lease_id=ids["lease"],
                title="lost lease",
                objective="bad",
                authorization={},
                correlation_id=str(uuid.uuid4()),
            )

    await engine.dispose()
