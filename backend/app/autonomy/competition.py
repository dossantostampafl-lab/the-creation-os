from __future__ import annotations

import asyncio
import json
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.diagnostics.heartbeat import supervised
from app.diagnostics.worker import creator_scope
from app.inference.agent_config import effective_agent_capabilities
from app.inference.bootstrap import build_model_router
from app.inference.contracts import (
    InferenceError,
    InferenceRateLimitError,
    InferenceRequest,
    ModelRequirements,
)
from app.inference.router import ModelRouter
from app.models.entities import Agent, Universe
from app.models.opportunity import Opportunity, OpportunityLease, OpportunityThesis
from app.observability.telemetry import traced
from app.repositories.domain import DomainRepository
from app.schemas.opportunity import OpportunityThesisCreate
from app.services.opportunity import (
    acquire_research_lease,
    release_lease,
    resolve_competition,
    submit_thesis,
)


class GeneratedThesis(BaseModel):
    proposed_value: str = Field(..., min_length=1, max_length=8000)
    target_payer: str = Field(..., min_length=1, max_length=4000)
    capture_path: str = Field(..., min_length=1, max_length=4000)
    estimated_cost: dict[str, Any] = Field(default_factory=dict)
    expected_value: dict[str, Any] = Field(default_factory=dict)
    max_downside: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(..., ge=0.0, le=1.0)
    falsification_conditions: list[str] = Field(..., min_length=1)


class ThesisGenerator(Protocol):
    async def generate(
        self, opportunity: Opportunity, universe: Universe, agent: Agent
    ) -> OpportunityThesisCreate: ...

    async def critique(
        self,
        opportunity: Opportunity,
        theses: list[OpportunityThesis],
        universe: Universe,
        agent: Agent,
    ) -> dict[str, Any]: ...

    async def compose(
        self,
        opportunity: Opportunity,
        theses: list[OpportunityThesis],
        critique: dict[str, Any],
        universe: Universe,
        agent: Agent,
    ) -> OpportunityThesisCreate: ...


def next_cycle_delay(
    base_seconds: float, consecutive_unavailable: int, max_seconds: float
) -> float:
    """Doubles the wait after each cycle in which no inference provider answered.

    Free-tier quotas recover on the provider's clock, not ours: retrying every cycle while
    they are exhausted only keeps them exhausted, and leaves nothing for DEUS to answer with.
    """
    if consecutive_unavailable <= 0:
        return base_seconds
    return min(base_seconds * 2 ** min(consecutive_unavailable, 16), max(base_seconds, max_seconds))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _amount(value: dict[str, Any]) -> float:
    raw = value.get("amount", 0.0)
    try:
        parsed = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(parsed):
        return 0.0
    return max(0.0, parsed)


def score_thesis(thesis: OpportunityThesis) -> float:
    confidence = max(0.0, min(1.0, float(thesis.confidence)))
    cost = _amount(dict(thesis.estimated_cost_json or {}))
    expected = _amount(dict(thesis.expected_value_json or {}))
    downside = _amount(dict(thesis.max_downside_json or {}))
    value_efficiency = expected / (expected + cost + 1.0)
    downside_safety = 1.0 / (1.0 + downside)
    score = 0.55 * confidence + 0.30 * value_efficiency + 0.15 * downside_safety
    return max(0.0, min(1.0, score))


def _json_object(content: str) -> dict[str, Any]:
    raw = content.strip()
    fence = chr(96) * 3
    if raw.startswith(fence):
        lines = raw.splitlines()
        if lines and lines[0].startswith(fence):
            lines = lines[1:]
        if lines and lines[-1].strip() == fence:
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("inference response must be a JSON object")
    return value


class InferenceThesisGenerator:
    def __init__(self, router: ModelRouter) -> None:
        self.router = router

    @staticmethod
    def _requirements(agent: Agent) -> tuple[str, list[str], str | None]:
        capabilities = effective_agent_capabilities(dict(agent.capabilities_json or {}))
        preferred = str(
            capabilities.get("inference_provider") or settings.llm_provider
        ).strip().lower()
        raw_fallbacks = capabilities.get("fallback_providers", [])
        fallbacks = (
            [str(item).strip().lower() for item in raw_fallbacks if str(item).strip()]
            if isinstance(raw_fallbacks, list)
            else []
        )
        if not fallbacks and preferred == settings.inference_provider_chain[0]:
            fallbacks = settings.inference_provider_chain[1:]
        model = capabilities.get("model")
        return preferred, fallbacks, str(model) if model else None

    async def _ask(
        self, agent: Agent, system: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        preferred, fallbacks, model = self._requirements(agent)
        response = await self.router.generate(
            InferenceRequest(
                messages=[
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": json.dumps(
                            payload,
                            sort_keys=True,
                            ensure_ascii=False,
                            default=str,
                        ),
                    },
                ],
                model=model,
                requirements=ModelRequirements(
                    preferred_provider=preferred,
                    fallback_providers=fallbacks,
                ),
                metadata={
                    "cache_policy": "bypass",
                    "cache_intent": "SYSTEM_COMMAND",
                    "cache_sensitivity": "PRIVATE",
                },
            )
        )
        return _json_object(response.content)

    @staticmethod
    def _opportunity_payload(opportunity: Opportunity) -> dict[str, Any]:
        return {
            "opportunity_id": opportunity.id,
            "sector": opportunity.sector,
            "problem_or_gap": opportunity.problem_or_gap,
            "capture_mechanism": opportunity.capture_mechanism,
            "evidence_refs": list(opportunity.evidence_refs_json or []),
            "time_window": dict(opportunity.time_window_json or {}),
        }

    @staticmethod
    def _to_create(
        opportunity: Opportunity,
        generated: GeneratedThesis,
        *,
        extra_evidence: list[str] | None = None,
    ) -> OpportunityThesisCreate:
        evidence = list(
            dict.fromkeys(
                [
                    *list(opportunity.evidence_refs_json or []),
                    *list(extra_evidence or []),
                ]
            )
        )
        return OpportunityThesisCreate(
            creator_id=opportunity.creator_id,
            proposed_value=generated.proposed_value,
            target_payer=generated.target_payer,
            capture_path=generated.capture_path,
            estimated_cost=generated.estimated_cost,
            expected_value=generated.expected_value,
            max_downside=generated.max_downside,
            confidence=generated.confidence,
            falsification_conditions=generated.falsification_conditions,
            evidence_refs=evidence,
        )

    async def generate(
        self, opportunity: Opportunity, universe: Universe, agent: Agent
    ) -> OpportunityThesisCreate:
        description = str(
            (agent.capabilities_json or {}).get("description", universe.name)
        )
        raw = await self._ask(
            agent,
            (
                "You are one specialized Universe in THE CREATION OS. Produce one falsifiable "
                "opportunity thesis from the supplied evidence. Do not take external actions and "
                "do not claim authority. Return JSON only with keys: proposed_value, target_payer, "
                "capture_path, estimated_cost, expected_value, max_downside, confidence, "
                "falsification_conditions. Monetary mappings should use currency and amount."
            ),
            {
                "universe": {
                    "code": universe.code,
                    "name": universe.name,
                    "specialization": description,
                },
                "opportunity": self._opportunity_payload(opportunity),
            },
        )
        generated = GeneratedThesis.model_validate(raw)
        return self._to_create(opportunity, generated)

    async def critique(
        self,
        opportunity: Opportunity,
        theses: list[OpportunityThesis],
        universe: Universe,
        agent: Agent,
    ) -> dict[str, Any]:
        return await self._ask(
            agent,
            (
                "Critique competing opportunity theses using only the supplied evidence. "
                "Identify concrete weaknesses, falsification risks and useful complementary parts. "
                "Do not authorize execution. Return one JSON object only."
            ),
            {
                "universe": {"code": universe.code, "name": universe.name},
                "opportunity": self._opportunity_payload(opportunity),
                "theses": [
                    {
                        "id": item.id,
                        "universe_id": item.universe_id,
                        "proposed_value": item.proposed_value,
                        "target_payer": item.target_payer,
                        "capture_path": item.capture_path,
                        "estimated_cost": item.estimated_cost_json,
                        "expected_value": item.expected_value_json,
                        "max_downside": item.max_downside_json,
                        "confidence": item.confidence,
                        "falsification_conditions": item.falsification_conditions_json,
                    }
                    for item in theses
                ],
            },
        )

    async def compose(
        self,
        opportunity: Opportunity,
        theses: list[OpportunityThesis],
        critique: dict[str, Any],
        universe: Universe,
        agent: Agent,
    ) -> OpportunityThesisCreate:
        raw = await self._ask(
            agent,
            (
                "Compose a stronger falsifiable thesis from the competing theses and critique. "
                "Use only supplied evidence and preserve bounded downside. Do not authorize execution. "
                "Return JSON only with keys: proposed_value, target_payer, capture_path, estimated_cost, "
                "expected_value, max_downside, confidence, falsification_conditions."
            ),
            {
                "universe": {"code": universe.code, "name": universe.name},
                "opportunity": self._opportunity_payload(opportunity),
                "critique": critique,
                "theses": [
                    {
                        "id": item.id,
                        "universe_id": item.universe_id,
                        "proposed_value": item.proposed_value,
                        "target_payer": item.target_payer,
                        "capture_path": item.capture_path,
                        "estimated_cost": item.estimated_cost_json,
                        "expected_value": item.expected_value_json,
                        "max_downside": item.max_downside_json,
                        "confidence": item.confidence,
                        "falsification_conditions": item.falsification_conditions_json,
                    }
                    for item in theses
                ],
            },
        )
        generated = GeneratedThesis.model_validate(raw)
        return self._to_create(
            opportunity,
            generated,
            extra_evidence=[
                f"composition:{opportunity.id}",
                *[f"thesis:{item.id}" for item in theses],
            ],
        )


class OpportunityCompetitionWorker:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        generator: ThesisGenerator,
        competitor_universe_ids: list[str] | None = None,
        competitor_limit: int = 3,
        composition_enabled: bool = True,
        max_opportunities_per_cycle: int = 2,
        research_lease_seconds: int = 600,
        executive_lease_seconds: int = 1800,
        stale_claim_seconds: int = 900,
    ) -> None:
        if competitor_limit < 2:
            raise ValueError("competitor_limit must be >= 2")
        if max_opportunities_per_cycle < 1:
            raise ValueError("max_opportunities_per_cycle must be >= 1")
        self.factory = factory
        self.generator = generator
        self.competitor_universe_ids = list(competitor_universe_ids or [])
        self.competitor_limit = competitor_limit
        self.composition_enabled = composition_enabled
        self.max_opportunities_per_cycle = max_opportunities_per_cycle
        self.research_lease_seconds = research_lease_seconds
        self.executive_lease_seconds = executive_lease_seconds
        self.stale_claim_seconds = stale_claim_seconds
        # Provider chains that answered no request this cycle. Agents can pin different
        # chains, so one exhausted chain only stops the calls that would use it again.
        self._unavailable_chains: set[tuple[str, tuple[str, ...], str | None]] = set()
        self._inference_answered = False
        self._inference_rate_limited = False

    @staticmethod
    def _chain(agent: Agent) -> tuple[str, tuple[str, ...], str | None]:
        preferred, fallbacks, model = InferenceThesisGenerator._requirements(agent)
        return preferred, tuple(fallbacks), model

    def _note_inference_failure(self, agent: Agent, exc: Exception) -> None:
        if isinstance(exc, InferenceError):
            self._unavailable_chains.add(self._chain(agent))
            if isinstance(exc, InferenceRateLimitError):
                self._inference_rate_limited = True

    @staticmethod
    def _composer(competitors: list[tuple[Universe, Agent]]) -> tuple[Universe, Agent]:
        return next(
            (pair for pair in competitors if pair[0].code == "evolution"),
            competitors[0],
        )

    async def _claim(self, creator_id: str) -> list[str]:
        stale_before = _utcnow() - timedelta(seconds=self.stale_claim_seconds)
        async with self.factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(Opportunity)
                        .where(
                            Opportunity.creator_id == creator_id,
                            or_(
                                Opportunity.status == "DETECTED",
                                (
                                    (Opportunity.status == "RESEARCHING")
                                    & (Opportunity.updated_at < stale_before)
                                ),
                            ),
                        )
                        .order_by(Opportunity.created_at.asc(), Opportunity.id.asc())
                        .limit(self.max_opportunities_per_cycle)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            for item in rows:
                item.status = "RESEARCHING"
                item.updated_at = _utcnow()
            await session.commit()
            return [item.id for item in rows]

    async def _competitors(
        self, session: AsyncSession, opportunity: Opportunity
    ) -> list[tuple[Universe, Agent]]:
        query = (
            select(Universe, Agent)
            .join(Agent, Agent.universe_id == Universe.id)
            .where(Universe.active.is_(True), Agent.active.is_(True))
        )
        if self.competitor_universe_ids:
            query = query.where(Universe.id.in_(self.competitor_universe_ids))
        rows = list((await session.execute(query)).all())

        by_universe: dict[str, tuple[Universe, Agent]] = {}
        for universe, agent in rows:
            by_universe.setdefault(universe.id, (universe, agent))
        ordered = sorted(
            by_universe.values(),
            key=lambda pair: (
                0 if pair[0].id == opportunity.first_discovered_by_universe_id else 1,
                pair[0].code,
                pair[1].id,
            ),
        )
        return ordered[: self.competitor_limit]

    @staticmethod
    async def _active_research_lease(
        session: AsyncSession, thesis_id: str
    ) -> OpportunityLease | None:
        now = _utcnow()
        return await session.scalar(
            select(OpportunityLease).where(
                OpportunityLease.thesis_id == thesis_id,
                OpportunityLease.lease_type == "RESEARCH",
                OpportunityLease.status == "ACTIVE",
                OpportunityLease.expires_at > now,
            )
        )

    async def _research_lease(
        self,
        repository: DomainRepository,
        opportunity: Opportunity,
        thesis: OpportunityThesis,
        correlation_id: str,
    ) -> OpportunityLease:
        current = await self._active_research_lease(repository.session, thesis.id)
        if current is not None:
            return current
        return await acquire_research_lease(
            repository,
            opportunity_id=opportunity.id,
            thesis_id=thesis.id,
            universe_id=thesis.universe_id,
            expires_at=_utcnow() + timedelta(seconds=self.research_lease_seconds),
            correlation_id=correlation_id,
        )

    async def _reset_for_retry(self, opportunity_id: str) -> None:
        async with self.factory() as session:
            item = await session.get(Opportunity, opportunity_id)
            if item is not None and item.status == "RESEARCHING":
                item.status = "DETECTED"
                item.updated_at = _utcnow()
                await session.commit()

    async def _process(self, opportunity_id: str) -> tuple[int, bool]:
        correlation_id = str(uuid.uuid4())
        research_leases: list[OpportunityLease] = []
        theses_created = 0

        async with self.factory() as session:
            opportunity = await session.get(Opportunity, opportunity_id)
            if opportunity is None or opportunity.status != "RESEARCHING":
                return 0, False

            repository = DomainRepository(session)
            competitors = await self._competitors(session, opportunity)
            if len(competitors) < 2:
                opportunity.status = "DETECTED"
                await session.commit()
                return 0, False

            existing = list(
                (
                    await session.scalars(
                        select(OpportunityThesis).where(
                            OpportunityThesis.opportunity_id == opportunity.id
                        )
                    )
                ).all()
            )
            existing_universe_ids = {
                item.universe_id
                for item in existing
                if f"composition:{opportunity.id}"
                not in list(item.evidence_refs_json or [])
            }

            for universe, agent in competitors:
                if universe.id in existing_universe_ids:
                    continue
                if self._chain(agent) in self._unavailable_chains:
                    continue
                try:
                    thesis_payload = await self.generator.generate(
                        opportunity, universe, agent
                    )
                except Exception as exc:
                    self._note_inference_failure(agent, exc)
                    logger.bind(
                        component="opportunity-competition",
                        opportunity_id=opportunity.id,
                        universe=universe.code,
                        error_type=type(exc).__name__,
                    ).warning("opportunity thesis generation failed")
                    continue
                self._inference_answered = True

                thesis = await submit_thesis(
                    repository,
                    opportunity_id=opportunity.id,
                    universe_id=universe.id,
                    thesis=thesis_payload,
                    correlation_id=correlation_id,
                )
                existing.append(thesis)
                existing_universe_ids.add(universe.id)
                theses_created += 1

            if len(existing) < 2:
                opportunity = await session.get(Opportunity, opportunity.id)
                if opportunity is not None:
                    opportunity.status = "DETECTED"
                    await session.commit()
                return theses_created, False

            composition_marker = f"composition:{opportunity.id}"
            composer_universe, composer_agent = self._composer(competitors)
            if (
                self.composition_enabled
                and self._chain(composer_agent) in self._unavailable_chains
                and not any(
                    composition_marker in list(item.evidence_refs_json or [])
                    for item in existing
                )
            ):
                # The composer's chain did not answer this cycle. Resolving now would select
                # without the composition for good, so the theses wait for a later cycle.
                opportunity.status = "DETECTED"
                opportunity.updated_at = _utcnow()
                await session.commit()
                return theses_created, False

            for thesis in existing:
                research_leases.append(
                    await self._research_lease(
                        repository, opportunity, thesis, correlation_id
                    )
                )

            if self.composition_enabled:
                composed = next(
                    (
                        item
                        for item in existing
                        if composition_marker in list(item.evidence_refs_json or [])
                    ),
                    None,
                )
                if composed is None:
                    try:
                        critique = await self.generator.critique(
                            opportunity,
                            existing,
                            composer_universe,
                            composer_agent,
                        )
                        self._inference_answered = True
                        await repository.add_event(
                            "opportunity_theses_critiqued",
                            "opportunity",
                            opportunity.id,
                            composer_universe.id,
                            "universe",
                            correlation_id,
                            {
                                "thesis_ids": [item.id for item in existing],
                                "critique": critique,
                            },
                        )
                        await repository.commit()

                        composed_payload = await self.generator.compose(
                            opportunity,
                            existing,
                            critique,
                            composer_universe,
                            composer_agent,
                        )
                        refs = list(
                            dict.fromkeys(
                                [
                                    *composed_payload.evidence_refs,
                                    composition_marker,
                                    *[f"thesis:{item.id}" for item in existing],
                                ]
                            )
                        )
                        composed_payload = composed_payload.model_copy(
                            update={"evidence_refs": refs}
                        )
                        composed = await submit_thesis(
                            repository,
                            opportunity_id=opportunity.id,
                            universe_id=composer_universe.id,
                            thesis=composed_payload,
                            correlation_id=correlation_id,
                        )
                        existing.append(composed)
                        research_leases.append(
                            await self._research_lease(
                                repository,
                                opportunity,
                                composed,
                                correlation_id,
                            )
                        )
                        theses_created += 1
                        await repository.add_event(
                            "opportunity_composition_submitted",
                            "opportunity",
                            opportunity.id,
                            composer_universe.id,
                            "universe",
                            correlation_id,
                            {
                                "thesis_id": composed.id,
                                "source_thesis_ids": [
                                    item.id
                                    for item in existing
                                    if item.id != composed.id
                                ],
                            },
                        )
                        await repository.commit()
                    except Exception as exc:
                        self._note_inference_failure(composer_agent, exc)
                        logger.bind(
                            component="opportunity-competition",
                            opportunity_id=opportunity.id,
                            error_type=type(exc).__name__,
                        ).warning("opportunity thesis composition unavailable")

            scores = {item.id: score_thesis(item) for item in existing}
            await resolve_competition(
                repository,
                opportunity_id=opportunity.id,
                scores=scores,
                expires_at=_utcnow()
                + timedelta(seconds=self.executive_lease_seconds),
                correlation_id=correlation_id,
            )

            for lease in research_leases:
                await release_lease(
                    repository,
                    lease_id=lease.id,
                    universe_id=lease.universe_id,
                    correlation_id=correlation_id,
                )

            return theses_created, True

    @traced("opportunity.competition")
    async def run_once(self, creator_id: str) -> dict[str, int]:
        self._unavailable_chains = set()
        self._inference_answered = False
        self._inference_rate_limited = False
        claimed = await self._claim(creator_id)
        theses_created = 0
        competitions_resolved = 0
        for opportunity_id in claimed:
            try:
                created, resolved = await self._process(opportunity_id)
            except Exception as exc:
                await self._reset_for_retry(opportunity_id)
                logger.bind(
                    component="opportunity-competition",
                    opportunity_id=opportunity_id,
                    error_type=type(exc).__name__,
                ).warning("opportunity competition cycle failed")
                continue
            theses_created += created
            competitions_resolved += int(resolved)
        return {
            "opportunities_claimed": len(claimed),
            "opportunities_processed": competitions_resolved,
            "theses_created": theses_created,
            "competitions_resolved": competitions_resolved,
            # Back off only when inference was needed and nothing answered: a cycle in which
            # some chain still generated keeps the normal interval.
            "inference_unavailable": int(
                bool(self._unavailable_chains) and not self._inference_answered
            ),
            "inference_rate_limited": int(self._inference_rate_limited),
        }


async def run() -> None:
    if not settings.deus_autonomy_competition_enabled:
        logger.info("autonomous opportunity competition disabled by configuration")
        return

    worker = OpportunityCompetitionWorker(
        AsyncSessionLocal,
        generator=InferenceThesisGenerator(build_model_router(background=True)),
        competitor_limit=settings.opportunity_competitor_limit,
        composition_enabled=settings.opportunity_composition_enabled,
        max_opportunities_per_cycle=settings.opportunity_max_per_cycle,
        research_lease_seconds=settings.opportunity_research_lease_seconds,
        executive_lease_seconds=settings.opportunity_executive_lease_seconds,
        stale_claim_seconds=settings.opportunity_stale_claim_seconds,
    )
    consecutive_unavailable = 0
    while True:
        try:
            creator_id = await creator_scope()
            if creator_id:
                report = await worker.run_once(creator_id)
                if report["inference_unavailable"]:
                    consecutive_unavailable += 1
                else:
                    consecutive_unavailable = 0
                logger.bind(**report).info(
                    "autonomous opportunity competition cycle"
                )
        except Exception as exc:
            logger.bind(
                component="opportunity-competition",
                error_type=type(exc).__name__,
            ).warning("opportunity competition worker unavailable")
        delay = next_cycle_delay(
            settings.opportunity_competition_cycle_seconds,
            consecutive_unavailable,
            settings.opportunity_inference_backoff_max_seconds,
        )
        if consecutive_unavailable:
            logger.bind(
                component="opportunity-competition",
                consecutive_unavailable=consecutive_unavailable,
                delay_seconds=delay,
            ).warning("no inference provider answered; backing off the next cycle")
        await asyncio.sleep(delay)


if __name__ == "__main__":
    asyncio.run(supervised("opportunity-worker", run))
