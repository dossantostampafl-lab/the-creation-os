from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.entities import Creator, Universe
from app.repositories.domain import DomainRepository
from app.services.domain import NotFoundError
from app.services.economy import (
    EconomicPolicyError,
    append_ledger_entry,
    ensure_genesis_allocation,
    project_universe_economy,
)

pytestmark = pytest.mark.integration


async def _seed(factory) -> dict[str, str]:
    creator = str(uuid.uuid4())
    other = str(uuid.uuid4())
    universe = str(uuid.uuid4())
    async with factory() as session:
        session.add_all([
            Creator(id=creator, username=f"creator-{creator[:8]}", password_hash="x", is_active=True),
            Creator(id=other, username=f"creator-{other[:8]}", password_hash="x", is_active=True),
            Universe(id=universe, code=f"u-{universe[:8]}", name="Economy", active=True),
        ])
        await session.commit()
    return {"creator": creator, "other": other, "universe": universe}


@pytest.mark.asyncio
async def test_ledger_projection_is_append_only_creator_scoped_and_ignores_simulated_profit() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids = await _seed(factory)

    async with factory() as session:
        repo = DomainRepository(session)
        base = dict(
            repository=repo, creator_id=ids["creator"], universe_id=ids["universe"],
            mission_id=None, opportunity_id=None, currency="BRL", correlation_id=str(uuid.uuid4()),
        )
        await append_ledger_entry(**base, entry_type="GENESIS", amount=Decimal("10"), status="SETTLED",
                                  external_reference="genesis", metadata={"mode": "real"})
        await append_ledger_entry(**base, entry_type="RESERVE", amount=Decimal("1"), status="RESERVED",
                                  external_reference="r1", metadata={"mode": "real"})
        await append_ledger_entry(**base, entry_type="PROFIT", amount=Decimal("50"), status="SETTLED",
                                  external_reference="paper-profit", metadata={"mode": "paper"})
        projection = await project_universe_economy(
            session, creator_id=ids["creator"], universe_id=ids["universe"], currency="BRL"
        )
        assert projection.nav == Decimal("10")
        assert projection.available == Decimal("9")
        assert projection.reserved == Decimal("1")
        assert projection.settled_pnl == 0

        other = await project_universe_economy(
            session, creator_id=ids["other"], universe_id=ids["universe"], currency="BRL"
        )
        assert other.nav == 0
        assert other.available == 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_unknown_freezes_state_until_reconciliation_and_loss_suspends() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids = await _seed(factory)

    async with factory() as session:
        repo = DomainRepository(session)
        common = dict(
            repository=repo, creator_id=ids["creator"], universe_id=ids["universe"],
            mission_id=None, opportunity_id=None, currency="BRL", correlation_id=str(uuid.uuid4()),
        )
        await append_ledger_entry(**common, entry_type="GENESIS", amount=Decimal("10"), status="SETTLED",
                                  external_reference="g", metadata={"mode": "real"})
        await append_ledger_entry(**common, entry_type="LOSS", amount=Decimal("2"), status="SETTLED",
                                  external_reference="loss", metadata={"mode": "real"})
        await append_ledger_entry(**common, entry_type="UNKNOWN", amount=Decimal("1"), status="UNKNOWN",
                                  external_reference="effect-1", metadata={"mode": "real"})
        projection = await project_universe_economy(
            session, creator_id=ids["creator"], universe_id=ids["universe"], currency="BRL"
        )
        assert projection.nav == Decimal("8")
        assert projection.economic_status == "RECONCILIATION_REQUIRED"
        assert projection.reconciliation_backlog == 1

        await append_ledger_entry(**common, entry_type="RECONCILED", amount=Decimal("1"), status="RECONCILED",
                                  external_reference="effect-1",
                                  metadata={"mode": "real", "unknown_reference": "effect-1"})
        projection = await project_universe_economy(
            session, creator_id=ids["creator"], universe_id=ids["universe"], currency="BRL"
        )
        assert projection.reconciliation_backlog == 0
        assert projection.economic_status == "ECONOMIC_SUSPENDED"

    await engine.dispose()


@pytest.mark.asyncio
async def test_genesis_requires_explicit_real_mode_and_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids = await _seed(factory)

    async with factory() as session:
        repo = DomainRepository(session)
        monkeypatch.setattr(settings, "real_economic_mode_enabled", False)
        with pytest.raises(EconomicPolicyError):
            await ensure_genesis_allocation(
                repo, creator_id=ids["creator"], universe_id=ids["universe"], correlation_id=str(uuid.uuid4())
            )
        monkeypatch.setattr(settings, "real_economic_mode_enabled", True)
        first = await ensure_genesis_allocation(
            repo, creator_id=ids["creator"], universe_id=ids["universe"], correlation_id=str(uuid.uuid4())
        )
        second = await ensure_genesis_allocation(
            repo, creator_id=ids["creator"], universe_id=ids["universe"], correlation_id=str(uuid.uuid4())
        )
        assert first.id == second.id

    await engine.dispose()


@pytest.mark.asyncio
async def test_ledger_rejects_cross_creator_mission_or_opportunity_scope() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids = await _seed(factory)
    async with factory() as session:
        repo = DomainRepository(session)
        with pytest.raises(NotFoundError):
            await append_ledger_entry(
                repo, creator_id=str(uuid.uuid4()), universe_id=ids["universe"], mission_id=None,
                opportunity_id=None, entry_type="GENESIS", amount=Decimal("1"), currency="BRL",
                status="SETTLED", external_reference="foreign", metadata={"mode": "real"},
                correlation_id=str(uuid.uuid4()),
            )
    await engine.dispose()
