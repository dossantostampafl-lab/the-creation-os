from __future__ import annotations

import asyncio
import copy
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from db_safety import create_isolated_test_engine, validated_test_database_url
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_consolidation_integration import source_snapshot

from app.config import settings
from app.main import app
from app.models.consolidation import MissionConsolidation
from app.models.decision import MissionDecision
from app.repositories.consolidation import ConsolidationRepository
from app.repositories.decision import DecisionRepository
from app.services.consolidation import ConsolidationService
from app.services.decision import DecisionService

pytestmark = pytest.mark.integration
pytest_plugins = ["test_consolidation_integration"]


def auth(subject: str) -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": subject,
            "type": "access",
            "jti": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def run_alembic(revision: str, operation: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = validated_test_database_url()
    subprocess.run(
        [sys.executable, "-m", "alembic", operation, revision],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.asyncio
async def test_0010_migration_round_trip_constraints_and_triggers():
    run_alembic("0009_tree_core_consolidation", "downgrade")
    engine = create_isolated_test_engine()
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0009_tree_core_consolidation"
        assert await connection.scalar(text("SELECT to_regclass('public.mission_decisions')")) is None
    await engine.dispose()

    run_alembic("0010_central_core_decision", "upgrade")
    engine = create_isolated_test_engine()
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0010_central_core_decision"
        assert await connection.scalar(text("SELECT to_regclass('public.mission_decisions')")) == "mission_decisions"
        constraints = set(
            (
                await connection.scalars(
                    text("SELECT conname FROM pg_constraint WHERE conrelid='mission_decisions'::regclass")
                )
            ).all()
        )
        assert constraints >= {
            "mission_decisions_pkey",
            "mission_decisions_mission_id_fkey",
            "mission_decisions_consolidation_id_fkey",
            "uq_mission_decision_mission",
            "ck_mission_decision_state",
            "ck_mission_decision_fingerprint",
        }
        assert await connection.scalar(
            text("SELECT count(*) FROM pg_trigger WHERE tgname='trg_mission_decision_immutable' AND NOT tgisinternal")
        ) == 1
    await engine.dispose()

    run_alembic("0009_tree_core_consolidation", "downgrade")
    engine = create_isolated_test_engine()
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0009_tree_core_consolidation"
        assert await connection.scalar(text("SELECT to_regclass('public.mission_decisions')")) is None
    await engine.dispose()
    run_alembic("0010_central_core_decision", "upgrade")


async def create_complete_consolidation(factory, mission_id: str) -> MissionConsolidation:
    async with factory() as session:
        item, created = await ConsolidationService(ConsolidationRepository(session)).consolidate(mission_id)
        assert created
        return item


async def consolidation_snapshot(factory, mission_id: str):
    async with factory() as session:
        item = await session.scalar(
            select(MissionConsolidation).where(MissionConsolidation.mission_id == mission_id)
        )
        if item is None:
            return None
        return copy.deepcopy(
            (
                item.id,
                item.mission_id,
                item.status,
                item.payload_json,
                item.inconsistencies_json,
                item.completeness_json,
                item.fingerprint,
                item.created_at,
                item.updated_at,
            )
        )


@pytest.mark.asyncio
async def test_http_decision_idempotency_security_and_get_without_creation(consolidation_db):
    factory, ids = consolidation_db
    path = f"/api/v1/central-core/missions/{ids['mission']}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(f"{path}/decision", headers=auth(ids["creator"]))).status_code == 404
        assert (await client.post(f"{path}/decide")).status_code == 401
        assert (await client.post(f"{path}/decide", headers=auth(str(uuid.uuid4())))).status_code == 403

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(MissionDecision)) == 0
    await create_complete_consolidation(factory, ids["mission"])
    before_sources = await source_snapshot(factory, ids)
    before_consolidation = await consolidation_snapshot(factory, ids["mission"])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(f"{path}/decide", headers=auth(ids["creator"]))
        assert created.status_code == 201 and created.json()["decision"] == "APPROVED"
        assert created.json()["justification"]["technical_readiness"] is True
        repeated = await client.post(f"{path}/decide", headers=auth(ids["creator"]))
        assert repeated.status_code == 200 and repeated.json() == created.json()
        queried = await client.get(f"{path}/decision", headers=auth(ids["creator"]))
        assert queried.status_code == 200 and queried.json() == created.json()
        assert (
            await client.get("/api/v1/central-core/missions/not-a-uuid/decision", headers=auth(ids["creator"]))
        ).status_code == 422
        missing = str(uuid.uuid4())
        assert (
            await client.post(f"/api/v1/central-core/missions/{missing}/decide", headers=auth(ids["creator"]))
        ).status_code == 404

    assert await source_snapshot(factory, ids) == before_sources
    assert await consolidation_snapshot(factory, ids["mission"]) == before_consolidation


@pytest.mark.asyncio
async def test_missing_consolidation_creates_requires_review(consolidation_db):
    factory, ids = consolidation_db
    async with factory() as session:
        item, created = await DecisionService(DecisionRepository(session)).decide(ids["mission"])
        assert created and item.decision == "REQUIRES_REVIEW"
        assert item.consolidation_id is None and item.consolidation_fingerprint is None
        assert {reason["code"] for reason in item.justification_json["reasons"]} == {"consolidation_missing"}


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["incomplete", "inconsistent"])
async def test_unready_consolidation_requires_review(consolidation_db, case):
    factory, ids = consolidation_db
    inconsistencies = [{"code": "blocking", "detail": "technical mismatch"}] if case == "inconsistent" else []
    completeness = {
        "complete": case != "incomplete",
        "expected_tasks": 2,
        "consolidated_tasks": 1 if case == "incomplete" else 2,
        "pending_tasks": 1 if case == "incomplete" else 0,
    }
    async with factory() as session:
        consolidation = MissionConsolidation(
            mission_id=ids["mission"],
            status="complete",
            payload_json={"mission_id": ids["mission"], "task_count": 2},
            inconsistencies_json=inconsistencies,
            completeness_json=completeness,
            fingerprint="b" * 64,
        )
        session.add(consolidation)
        await session.commit()
    async with factory() as session:
        item, _ = await DecisionService(DecisionRepository(session)).decide(ids["mission"])
        assert item.decision == "REQUIRES_REVIEW"
        codes = {reason["code"] for reason in item.justification_json["reasons"]}
        assert ("blocking_inconsistencies" if case == "inconsistent" else "completeness_not_confirmed") in codes


@pytest.mark.asyncio
async def test_real_postgresql_concurrency_and_unique_decision(consolidation_db):
    factory, ids = consolidation_db
    await create_complete_consolidation(factory, ids["mission"])

    async def decide_once():
        async with factory() as session:
            item, created = await DecisionService(DecisionRepository(session)).decide(ids["mission"])
            return item.id, created, item.consolidation_fingerprint

    results = await asyncio.gather(decide_once(), decide_once())
    assert {result[1] for result in results} == {True, False}
    assert results[0][0] == results[1][0]
    assert results[0][2] == results[1][2]
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(MissionDecision)) == 1


class FailingCommitRepository(DecisionRepository):
    async def commit(self):
        await self.session.rollback()
        raise RuntimeError("forced decision failure")


@pytest.mark.asyncio
async def test_decision_rollback_leaves_no_partial_row(consolidation_db):
    factory, ids = consolidation_db
    consolidation = await create_complete_consolidation(factory, ids["mission"])
    before_sources = await source_snapshot(factory, ids)
    before_consolidation = await consolidation_snapshot(factory, ids["mission"])
    async with factory() as session:
        with pytest.raises(RuntimeError, match="forced decision failure"):
            await DecisionService(FailingCommitRepository(session)).decide(ids["mission"])
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(MissionDecision)) == 0
        assert await session.get(MissionConsolidation, consolidation.id) is not None
    assert await source_snapshot(factory, ids) == before_sources
    assert await consolidation_snapshot(factory, ids["mission"]) == before_consolidation


@pytest.mark.asyncio
async def test_decision_database_immutability_and_unique_constraint(consolidation_db):
    factory, ids = consolidation_db
    await create_complete_consolidation(factory, ids["mission"])
    async with factory() as session:
        decision, _ = await DecisionService(DecisionRepository(session)).decide(ids["mission"])
        decision_id = decision.id
        consolidation_id = decision.consolidation_id
        consolidation_fingerprint = decision.consolidation_fingerprint
        with pytest.raises(DBAPIError, match="immutable"):
            await session.execute(
                text("UPDATE mission_decisions SET decision='REJECTED' WHERE id=:id"), {"id": decision_id}
            )
        await session.rollback()
        with pytest.raises(DBAPIError, match="immutable"):
            await session.execute(text("DELETE FROM mission_decisions WHERE id=:id"), {"id": decision_id})
        await session.rollback()

        session.add(
            MissionDecision(
                mission_id=ids["mission"],
                consolidation_id=consolidation_id,
                decision="APPROVED",
                justification_json={},
                consolidation_fingerprint=consolidation_fingerprint,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
