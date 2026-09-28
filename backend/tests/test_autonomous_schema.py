from __future__ import annotations

import importlib
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.entities import Conversation, Creator, Inception, Message, Mission, Universe

pytestmark = pytest.mark.integration


def _models():
    opportunity = importlib.import_module("app.models.opportunity")
    economy = importlib.import_module("app.models.economy")
    return (
        opportunity.Opportunity,
        opportunity.OpportunityThesis,
        opportunity.OpportunityLease,
        economy.EconomicLedgerEntry,
    )


def test_persistent_models_publish_required_tables_and_fields() -> None:
    Opportunity, OpportunityThesis, OpportunityLease, EconomicLedgerEntry = _models()

    expected = {
        Opportunity: {
            "id", "creator_id", "fingerprint", "sector", "problem_or_gap", "capture_mechanism",
            "evidence_refs_json", "first_discovered_by_universe_id", "time_window_json", "status",
            "created_at", "updated_at",
        },
        OpportunityThesis: {
            "id", "opportunity_id", "universe_id", "proposed_value", "target_payer", "capture_path",
            "estimated_cost_json", "expected_value_json", "max_downside_json", "confidence",
            "falsification_conditions_json", "evidence_refs_json", "status", "created_at", "updated_at",
        },
        OpportunityLease: {
            "id", "opportunity_id", "thesis_id", "universe_id", "lease_type", "status",
            "acquired_at", "expires_at", "released_at",
        },
        EconomicLedgerEntry: {
            "id", "creator_id", "universe_id", "mission_id", "opportunity_id", "entry_type",
            "amount", "currency", "status", "external_reference", "metadata_json", "created_at", "settled_at",
        },
    }
    for model, columns in expected.items():
        assert columns <= set(model.__table__.c.keys())

    opportunity_uniques = [
        constraint for constraint in Opportunity.__table__.constraints if isinstance(constraint, UniqueConstraint)
    ]
    assert any({column.name for column in item.columns} == {"creator_id", "fingerprint"} for item in opportunity_uniques)

    executive_indexes = [index for index in OpportunityLease.__table__.indexes if isinstance(index, Index) and index.unique]
    assert any(
        {column.name for column in index.columns} == {"opportunity_id"}
        and "EXECUTIVE" in str(index.dialect_options["postgresql"].get("where"))
        and "ACTIVE" in str(index.dialect_options["postgresql"].get("where"))
        for index in executive_indexes
    )


def test_mission_origin_columns_are_nullable_but_database_xor_constrained() -> None:
    _models()
    assert Mission.__table__.c.inception_id.nullable is True
    assert Mission.__table__.c.opportunity_id.nullable is True
    checks = [constraint for constraint in Mission.__table__.constraints if isinstance(constraint, CheckConstraint)]
    assert any(constraint.name == "ck_mission_exactly_one_origin" for constraint in checks)


@pytest.mark.asyncio
async def test_database_accepts_each_single_origin_and_rejects_both_or_neither() -> None:
    Opportunity, _, _, _ = _models()
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)

    creator_id = str(uuid.uuid4())
    universe_id = str(uuid.uuid4())
    conversation_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    async with factory() as session:
        session.add(Creator(id=creator_id, username=f"creator-{creator_id[:8]}", password_hash="x", is_active=True))
        session.add(Universe(id=universe_id, code=f"u-{universe_id[:8]}", name="Schema Test", active=True))
        await session.flush()

        session.add(Conversation(id=conversation_id, creator_id=creator_id, title="schema"))
        await session.flush()

        message_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        for message_id in message_ids:
            session.add(Message(
                id=message_id,
                conversation_id=conversation_id,
                role="creator",
                actor_id=creator_id,
                correlation_id=str(uuid.uuid4()),
                content="schema test",
                route="TEST",
            ))
        await session.flush()

        inception_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        for inception_id, message_id in zip(inception_ids, message_ids, strict=True):
            session.add(Inception(
                id=inception_id,
                conversation_id=conversation_id,
                source_message_id=message_id,
                title="schema inception",
                description="schema test",
            ))
        opportunity_id = str(uuid.uuid4())
        session.add(Opportunity(
            id=opportunity_id,
            creator_id=creator_id,
            fingerprint=f"fp-{opportunity_id}",
            sector="software",
            problem_or_gap="schema gap",
            capture_mechanism="service",
            evidence_refs_json=["test:evidence"],
            first_discovered_by_universe_id=universe_id,
            time_window_json={"until": (now + timedelta(days=1)).isoformat()},
            status="DETECTED",
        ))
        await session.commit()

    async with factory() as session:
        session.add(Mission(
            id=str(uuid.uuid4()), inception_id=inception_ids[0], opportunity_id=None, creator_id=creator_id,
            title="creator mission", objective="creator path",
        ))
        session.add(Mission(
            id=str(uuid.uuid4()), inception_id=None, opportunity_id=opportunity_id, creator_id=creator_id,
            title="opportunity mission", objective="opportunity path",
        ))
        await session.commit()

    async with factory() as session:
        session.add(Mission(
            id=str(uuid.uuid4()), inception_id=None, opportunity_id=None, creator_id=creator_id,
            title="invalid none", objective="must fail",
        ))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async with factory() as session:
        session.add(Mission(
            id=str(uuid.uuid4()), inception_id=inception_ids[1], opportunity_id=opportunity_id, creator_id=creator_id,
            title="invalid both", objective="must fail",
        ))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    await engine.dispose()
