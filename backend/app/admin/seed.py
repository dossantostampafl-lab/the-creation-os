"""Seed the canonical Universes and minimal Agents required by the runtime."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.core.domain import Actor
from app.db.session import AsyncSessionLocal
from app.models.entities import Agent, Creator, Universe
from app.repositories.domain import DomainRepository
from app.services.domain import LivingCoreService



PERCEPTION_PROFILES: dict[str, dict[str, Any]] = {
    "knowledge": {"preferred_sensors": ["web.search", "web.fetch", "research.semantic", "workspace.read"], "detectors": ["information_gap", "pain_recurrence", "demand_gap"]},
    "engineering": {"preferred_sensors": ["web.search", "web.fetch", "specialized.web", "workspace.read"], "detectors": ["capability_gap", "efficiency_gap", "technology_shift"]},
    "security": {"preferred_sensors": ["web.search", "web.fetch", "specialized.web", "workspace.read"], "detectors": ["capability_gap", "technology_shift", "regulatory_change"]},
    "vision": {"preferred_sensors": ["web.search", "web.crawl", "research.semantic"], "detectors": ["trend_acceleration", "behavior_change", "temporal_window"]},
    "design": {"preferred_sensors": ["web.search", "web.extract", "browser.observe"], "detectors": ["pain_recurrence", "conversion_friction", "attention_gap"]},
    "business": {"preferred_sensors": ["web.search", "web.crawl", "specialized.web"], "detectors": ["demand_gap", "supply_scarcity", "price_gap", "arbitrage"]},
    "marketing": {"preferred_sensors": ["web.search", "web.crawl", "research.semantic"], "detectors": ["attention_gap", "demand_gap", "trend_acceleration", "conversion_friction"]},
    "legal": {"preferred_sensors": ["web.search", "web.fetch", "research.semantic", "workspace.read"], "detectors": ["regulatory_change", "information_gap", "pain_recurrence"]},
    "finance": {"preferred_sensors": ["market.read", "web.search", "web.fetch", "proto.read"], "detectors": ["price_gap", "arbitrage", "temporal_window", "capacity_mismatch"]},
    "automation": {"preferred_sensors": ["web.search", "specialized.web", "workspace.read"], "detectors": ["efficiency_gap", "capability_gap", "capacity_mismatch"]},
    "communication": {"preferred_sensors": ["web.search", "web.crawl", "research.semantic"], "detectors": ["attention_gap", "behavior_change", "demand_gap"]},
    "evolution": {"preferred_sensors": ["chronicle.read", "metrics.read", "workspace.read"], "detectors": ["efficiency_gap", "technology_shift", "behavior_change"]},
}


def canonical_perception_profile(universe_code: str) -> dict[str, Any]:
    try:
        raw = PERCEPTION_PROFILES[universe_code]
    except KeyError as exc:
        raise ValueError(f"unknown canonical Universe: {universe_code}") from exc
    return {
        "preferred_sensors": list(raw["preferred_sensors"]),
        "detector_weights": {detector: 1.0 for detector in raw["detectors"]},
        "exploration_strategy": {
            "mode": "cross_sector",
            "exploration_weight": 0.25,
            "priors_are_permissions": False,
        },
    }

@dataclass(frozen=True)
class CanonicalUniverse:
    id: str
    code: str
    name: str
    description: str
    active: bool = True

    @property
    def agent_code(self) -> str:
        return f"{self.code}-agent"

    @property
    def agent_name(self) -> str:
        return f"{self.name} Agent"

    @property
    def capabilities(self) -> dict[str, Any]:
        return {
            "inference_provider": settings.llm_provider,
            "description": self.description,
            **canonical_perception_profile(self.code),
        }


CANONICAL_UNIVERSES: tuple[CanonicalUniverse, ...] = (
    CanonicalUniverse(
        "10000000-0000-0000-0000-000000000001",
        "knowledge",
        "Conhecimento",
        "Investiga, conecta e aplica conhecimento verificável.",
    ),
    CanonicalUniverse(
        "10000000-0000-0000-0000-000000000002",
        "engineering",
        "Engenharia",
        "Projeta, constrói, testa e melhora sistemas e produtos.",
    ),
    CanonicalUniverse(
        "10000000-0000-0000-0000-000000000003",
        "security",
        "Segurança",
        "Percebe riscos, fragilidades e oportunidades de proteção.",
    ),
    CanonicalUniverse(
        "10000000-0000-0000-0000-000000000004",
        "vision",
        "Visão",
        "Detecta sinais fracos, tendências e mudanças emergentes.",
    ),
    CanonicalUniverse(
        "10000000-0000-0000-0000-000000000005",
        "design",
        "Design",
        "Transforma necessidades em experiências e produtos úteis.",
    ),
    CanonicalUniverse(
        "10000000-0000-0000-0000-000000000006",
        "business",
        "Negócios",
        "Explora demanda, oferta, distribuição e modelos de receita.",
    ),
    CanonicalUniverse(
        "10000000-0000-0000-0000-000000000007",
        "marketing",
        "Marketing",
        "Percebe atenção, aquisição, posicionamento e conversão.",
    ),
    CanonicalUniverse(
        "10000000-0000-0000-0000-000000000008",
        "legal",
        "Jurídico",
        "Interpreta direitos, obrigações, restrições e mudanças normativas.",
    ),
    CanonicalUniverse(
        "10000000-0000-0000-0000-000000000009",
        "finance",
        "Finanças",
        "Analisa capital, liquidez, risco, preço e retorno.",
    ),
    CanonicalUniverse(
        "10000000-0000-0000-0000-000000000010",
        "automation",
        "Automação",
        "Descobre trabalho repetitivo e oportunidades de automação.",
    ),
    CanonicalUniverse(
        "10000000-0000-0000-0000-000000000011",
        "communication",
        "Comunicação",
        "Otimiza linguagem, relacionamento e distribuição de informação.",
    ),
    CanonicalUniverse(
        "10000000-0000-0000-0000-000000000012",
        "evolution",
        "Evolução",
        "Aprende com resultados e propõe melhorias ao próprio Creation.",
    ),
)


async def seed_universes() -> int:
    """Reconcile the canonical Universes idempotently and ensure minimal staffing."""
    async with AsyncSessionLocal() as session:
        creator = await session.scalar(select(Creator).limit(1))
        if creator is None:
            print(json.dumps({"seeded": False, "reason": "no_creator_yet"}))
            return 1
        if settings.sovereign_creator_id and settings.sovereign_creator_id != creator.id:
            print(json.dumps({"seeded": False, "reason": "creator_is_not_the_sovereign"}))
            return 1

        actor = Actor(creator.id, "creator")
        repository = DomainRepository(session)
        service = LivingCoreService(repository)
        created: list[str] = []
        activated: list[str] = []
        staffed: list[str] = []

        for spec in CANONICAL_UNIVERSES:
            universe = await session.scalar(select(Universe).where(Universe.code == spec.code))
            if universe is None:
                universe = await repository.add(
                    Universe(id=spec.id, code=spec.code, name=spec.name, active=spec.active)
                )
                if universe is None:
                    raise RuntimeError(f"failed to create canonical universe: {spec.code}")
                correlation_id = str(uuid.uuid4())
                await repository.add_event(
                    "universe_created",
                    "universe",
                    universe.id,
                    actor.id,
                    actor.role,
                    correlation_id,
                    {"code": spec.code, "canonical": True},
                )
                await repository.add_event(
                    "universe_activated",
                    "universe",
                    universe.id,
                    actor.id,
                    actor.role,
                    correlation_id,
                )
                await repository.commit()
                created.append(spec.code)
                activated.append(spec.code)
            elif not universe.active:
                await service.set_universe_active(actor, universe.id, True, str(uuid.uuid4()))
                activated.append(spec.code)

            agent = await session.scalar(select(Agent).where(Agent.code == spec.agent_code))
            if agent is None:
                await service.create_agent(
                    actor,
                    spec.agent_code,
                    spec.agent_name,
                    universe.id,
                    spec.capabilities,
                    str(uuid.uuid4()),
                )
                staffed.append(spec.agent_code)
            elif not agent.active:
                await service.set_agent_active(actor, agent.id, True, str(uuid.uuid4()))
                staffed.append(spec.agent_code)

            expected_capabilities = spec.capabilities
            if agent is not None and agent.capabilities_json != expected_capabilities:
                agent.capabilities_json = expected_capabilities
                await repository.add_event(
                    "agent_profile_reconciled",
                    "agent",
                    agent.id,
                    actor.id,
                    actor.role,
                    str(uuid.uuid4()),
                    {"universe_id": universe.id, "profile": "perception-priors-v1"},
                )
                await repository.commit()

        print(
            json.dumps(
                {
                    "seeded": True,
                    "universes_created": created,
                    "universes_activated": activated,
                    "agents_ready": staffed,
                }
            )
        )
        return 0


def main() -> None:
    raise SystemExit(asyncio.run(seed_universes()))


if __name__ == "__main__":
    main()
