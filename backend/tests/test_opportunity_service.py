from __future__ import annotations

import importlib
import os
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.entities import Creator, Universe
from app.repositories.domain import DomainRepository
from app.services.domain import NotFoundError

pytestmark = pytest.mark.integration


def _service():
    return importlib.import_module("app.services.opportunity")


def _schema():
    return importlib.import_module("app.schemas.opportunity")


def _discovery_kwargs(*, creator_id: str, universe_id: str) -> dict:
    return {
        "creator_id": creator_id,
        "discovered_by_universe_id": universe_id,
        "sector": " Software ",
        "problem_or_gap": "  Teams   lose context across AI agents ",
        "capture_mechanism": " Subscription Service ",
        "evidence_refs": ["https://example.test/evidence/1"],
        "time_window": {"until": "2026-12-31T23:59:59Z", "kind": "market"},
        "correlation_id": str(uuid.uuid4()),
    }


def test_normalized_equivalent_opportunities_have_same_fingerprint() -> None:
    normalize_opportunity_fingerprint = _service().normalize_opportunity_fingerprint
    left = normalize_opportunity_fingerprint(
        sector=" Software ",
        problem_or_gap="Teams   lose context across AI agents",
        capture_mechanism="Subscription Service",
        time_window={"until": "2026-12-31T23:59:59Z", "kind": "market"},
    )
    right = normalize_opportunity_fingerprint(
        sector="software",
        problem_or_gap=" teams lose CONTEXT across ai AGENTS ",
        capture_mechanism=" subscription   service ",
        time_window={"kind": "market", "until": "2026-12-31T23:59:59Z"},
    )
    assert left == right
    assert len(left) == 64


@pytest.mark.asyncio
async def test_create_or_get_dedupes_within_creator_but_not_across_creators() -> None:
    create_or_get_opportunity = _service().create_or_get_opportunity
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    creator_a = str(uuid.uuid4())
    creator_b = str(uuid.uuid4())
    universe_id = str(uuid.uuid4())

    async with factory() as session:
        session.add_all([
            Creator(id=creator_a, username=f"creator-{creator_a[:8]}", password_hash="x", is_active=True),
            Creator(id=creator_b, username=f"creator-{creator_b[:8]}", password_hash="x", is_active=True),
            Universe(id=universe_id, code=f"u-{universe_id[:8]}", name="Opportunity Test", active=True),
        ])
        await session.commit()

    async with factory() as session:
        repository = DomainRepository(session)
        first = await create_or_get_opportunity(repository, **_discovery_kwargs(creator_id=creator_a, universe_id=universe_id))
        same = await create_or_get_opportunity(
            repository,
            creator_id=creator_a,
            discovered_by_universe_id=universe_id,
            sector="software",
            problem_or_gap="teams lose CONTEXT across ai agents",
            capture_mechanism="subscription service",
            evidence_refs=["https://example.test/evidence/2"],
            time_window={"kind": "market", "until": "2026-12-31T23:59:59Z"},
            correlation_id=str(uuid.uuid4()),
        )
        other_creator = await create_or_get_opportunity(
            repository,
            **_discovery_kwargs(creator_id=creator_b, universe_id=universe_id),
        )

        assert first.id == same.id
        assert first.fingerprint == same.fingerprint
        assert other_creator.id != first.id
        assert other_creator.fingerprint == first.fingerprint
        assert sorted(same.evidence_refs_json) == [
            "https://example.test/evidence/1",
            "https://example.test/evidence/2",
        ]

    await engine.dispose()


@pytest.mark.asyncio
async def test_discovery_requires_evidence_and_thesis_is_creator_scoped() -> None:
    service = _service()
    OpportunityThesisCreate = _schema().OpportunityThesisCreate
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    creator_id = str(uuid.uuid4())
    other_creator_id = str(uuid.uuid4())
    universe_id = str(uuid.uuid4())

    async with factory() as session:
        session.add_all([
            Creator(id=creator_id, username=f"creator-{creator_id[:8]}", password_hash="x", is_active=True),
            Creator(id=other_creator_id, username=f"creator-{other_creator_id[:8]}", password_hash="x", is_active=True),
            Universe(id=universe_id, code=f"u-{universe_id[:8]}", name="Thesis Test", active=True),
        ])
        await session.commit()

    async with factory() as session:
        repository = DomainRepository(session)
        kwargs = _discovery_kwargs(creator_id=creator_id, universe_id=universe_id)
        kwargs["evidence_refs"] = []
        with pytest.raises(ValueError, match="evidence"):
            await service.create_or_get_opportunity(repository, **kwargs)

        kwargs["evidence_refs"] = ["https://example.test/evidence/owner"]
        opportunity = await service.create_or_get_opportunity(repository, **kwargs)

        with pytest.raises(ValidationError):
            OpportunityThesisCreate(
                creator_id=creator_id,
                proposed_value="Automate the missing workflow",
                target_payer="operations teams",
                capture_path="subscription",
                estimated_cost={},
                expected_value={},
                max_downside={},
                confidence=0.8,
                falsification_conditions=["no payer validation"],
                evidence_refs=[],
            )

        foreign_thesis = OpportunityThesisCreate(
            creator_id=other_creator_id,
            proposed_value="Automate the missing workflow",
            target_payer="operations teams",
            capture_path="subscription",
            estimated_cost={"amount": 1},
            expected_value={"amount": 3},
            max_downside={"amount": 1},
            confidence=0.8,
            falsification_conditions=["no payer validation"],
            evidence_refs=["https://example.test/evidence/thesis"],
        )
        with pytest.raises(NotFoundError):
            await service.submit_thesis(
                repository,
                opportunity_id=opportunity.id,
                universe_id=universe_id,
                thesis=foreign_thesis,
                correlation_id=str(uuid.uuid4()),
            )

    await engine.dispose()
