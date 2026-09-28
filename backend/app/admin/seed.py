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
