from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from test_knowledge import knowledge_db  # noqa: F401

from app.autonomy.competition import (
    OpportunityCompetitionWorker,
    score_thesis,
)
from app.models.entities import Agent, Chronicle, Mission, Universe
from app.models.opportunity import Opportunity, OpportunityLease, OpportunityThesis
from app.repositories.domain import DomainRepository
from app.schemas.opportunity import OpportunityThesisCreate
from app.services.opportunity import create_or_get_opportunity


class FakeThesisGenerator:
    def __init__(self) -> None:
        self.generated: list[str] = []
        self.critiques = 0
        self.compositions = 0

    async def generate(self, opportunity, universe, agent) -> OpportunityThesisCreate:
        self.generated.append(universe.id)
        index = len(self.generated)
        return OpportunityThesisCreate(
            creator_id=opportunity.creator_id,
            proposed_value=f"proposal-{universe.code}",
            target_payer="verified payer",
            capture_path="bounded service",
            estimated_cost={"currency": "BRL", "amount": 1},
            expected_value={"currency": "BRL", "amount": 2 + index},
            max_downside={"currency": "BRL", "amount": 1},
            confidence=min(0.55 + index * 0.08, 0.90),
            falsification_conditions=["payer rejects verified offer"],
            evidence_refs=list(opportunity.evidence_refs_json),
        )

    async def critique(self, opportunity, theses, universe, agent) -> dict:
        self.critiques += 1
        return {
            "critic_universe_id": universe.id,
            "weakest_thesis_id": min(theses, key=lambda item: item.confidence).id,
            "notes": "prefer verified upside with bounded downside",
        }

    async def compose(self, opportunity, theses, critique, universe, agent) -> OpportunityThesisCreate:
        self.compositions += 1
        return OpportunityThesisCreate(
            creator_id=opportunity.creator_id,
            proposed_value="composed best-of-theses",
            target_payer="verified payer",
            capture_path="bounded composed service",
            estimated_cost={"currency": "BRL", "amount": 1},
            expected_value={"currency": "BRL", "amount": 8},
            max_downside={"currency": "BRL", "amount": 1},
            confidence=0.95,
            falsification_conditions=["composition fails payer validation"],
            evidence_refs=list(opportunity.evidence_refs_json),
        )


@pytest.mark.asyncio
async def test_competition_worker_runs_theses_research_critique_composition_and_exec_lease_without_mission(
    knowledge_db,  # noqa: F811
) -> None:
    factory, creator_id, _ = knowledge_db
    universe_ids: list[str] = []

    async with factory() as session:
        for idx in range(3):
            universe_id = str(uuid.uuid4())
            universe_ids.append(universe_id)
            session.add(
                Universe(
                    id=universe_id,
                    code=f"competition-{idx}-{universe_id[:6]}",
                    name=f"Competition {idx}",
                    active=True,
                )
            )
            await session.flush()
            session.add(
                Agent(
                    id=str(uuid.uuid4()),
                    code=f"competition-agent-{idx}-{universe_id[:6]}",
                    name=f"Competition Agent {idx}",
                    universe_id=universe_id,
                    active=True,
                    capabilities_json={"inference_provider": "fake"},
                )
            )
        await session.commit()

    async with factory() as session:
        opportunity = await create_or_get_opportunity(
            DomainRepository(session),
            creator_id=creator_id,
            discovered_by_universe_id=universe_ids[0],
            sector="software",
            problem_or_gap="verified recurring operational gap",
            capture_mechanism="bounded service",
            evidence_refs=["test:competition:evidence"],
            time_window={"kind": "test"},
            correlation_id=str(uuid.uuid4()),
        )
        opportunity_id = opportunity.id

    generator = FakeThesisGenerator()
    worker = OpportunityCompetitionWorker(
        factory,
        generator=generator,
        competitor_universe_ids=universe_ids,
        competitor_limit=3,
        composition_enabled=True,
        max_opportunities_per_cycle=1,
        research_lease_seconds=300,
        executive_lease_seconds=900,
    )
    report = await worker.run_once(creator_id)

    assert report["opportunities_processed"] == 1
    assert report["theses_created"] == 4
    assert report["competitions_resolved"] == 1
    assert generator.critiques == 1
    assert generator.compositions == 1

    async with factory() as session:
        opportunity = await session.get(Opportunity, opportunity_id)
        assert opportunity is not None and opportunity.status == "SELECTED"

        theses = list(
            (
                await session.scalars(
                    select(OpportunityThesis).where(
                        OpportunityThesis.opportunity_id == opportunity_id
                    )
                )
            ).all()
        )
        assert len(theses) == 4
        selected = [item for item in theses if item.status == "SELECTED"]
        assert len(selected) == 1
        assert selected[0].proposed_value == "composed best-of-theses"

        active_exec = await session.scalar(
            select(func.count())
            .select_from(OpportunityLease)
            .where(
                OpportunityLease.opportunity_id == opportunity_id,
                OpportunityLease.lease_type == "EXECUTIVE",
                OpportunityLease.status == "ACTIVE",
            )
        )
        active_research = await session.scalar(
            select(func.count())
            .select_from(OpportunityLease)
            .where(
                OpportunityLease.opportunity_id == opportunity_id,
                OpportunityLease.lease_type == "RESEARCH",
                OpportunityLease.status == "ACTIVE",
            )
        )
        assert active_exec == 1
        assert active_research == 0
        assert not list(
            (
                await session.scalars(
                    select(Mission).where(Mission.opportunity_id == opportunity_id)
                )
            ).all()
        )

        events = {
            event.event_type
            for event in (
                await session.scalars(
                    select(Chronicle).where(Chronicle.aggregate_id == opportunity_id)
                )
            ).all()
        }
        assert "opportunity_theses_critiqued" in events
        assert "opportunity_composition_submitted" in events
        assert "opportunity_competition_resolved" in events

    second = await worker.run_once(creator_id)
    assert second["opportunities_processed"] == 0

    async with factory() as session:
        thesis_count = await session.scalar(
            select(func.count())
            .select_from(OpportunityThesis)
            .where(OpportunityThesis.opportunity_id == opportunity_id)
        )
        exec_count = await session.scalar(
            select(func.count())
            .select_from(OpportunityLease)
            .where(
                OpportunityLease.opportunity_id == opportunity_id,
                OpportunityLease.lease_type == "EXECUTIVE",
            )
        )
        assert thesis_count == 4
        assert exec_count == 1


def test_score_thesis_is_bounded_and_rewards_confidence_upside_and_downside_control() -> None:
    strong = OpportunityThesis(
        opportunity_id="opportunity",
        universe_id="universe",
        proposed_value="strong",
        target_payer="payer",
        capture_path="path",
        estimated_cost_json={"amount": 1},
        expected_value_json={"amount": 8},
        max_downside_json={"amount": 1},
        confidence=0.9,
        falsification_conditions_json=["condition"],
        evidence_refs_json=["evidence"],
    )
    weak = OpportunityThesis(
        opportunity_id="opportunity",
        universe_id="universe",
        proposed_value="weak",
        target_payer="payer",
        capture_path="path",
        estimated_cost_json={"amount": 4},
        expected_value_json={"amount": 2},
        max_downside_json={"amount": 5},
        confidence=0.4,
        falsification_conditions_json=["condition"],
        evidence_refs_json=["evidence"],
    )
    assert 0.0 <= score_thesis(weak) < score_thesis(strong) <= 1.0
