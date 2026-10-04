from __future__ import annotations

import asyncio
import hashlib
import json
import uuid

from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.autonomy.perception import PerceptionFabric, build_perception_fabric
from app.config import settings
from app.db.session import AsyncSessionLocal
from app.diagnostics.heartbeat import supervised
from app.diagnostics.worker import creator_scope
from app.knowledge.contracts import Scope
from app.knowledge.service import KnowledgeService
from app.models.entities import Agent, Universe
from app.models.opportunity import Opportunity
from app.repositories.domain import DomainRepository
from app.services.opportunity import create_or_get_opportunity, normalize_opportunity_fingerprint

KEYWORDS: dict[str, list[str]] = {
    "knowledge": ["conhecimento", "documentação", "informação", "pesquisa"],
    "engineering": ["engenharia", "software", "bug", "código", "latência"],
    "security": ["segurança", "vulnerabilidade", "credenciais", "ameaça"],
    "vision": ["tendência", "mudança", "emergente", "futuro"],
    "design": ["design", "interface", "usabilidade", "acessibilidade"],
    "business": ["negócio", "demanda", "cliente", "receita"],
    "marketing": ["marketing", "conversão", "campanha", "aquisição"],
    "legal": ["jurídico", "contrato", "regulação", "lei"],
    "finance": ["finanças", "preço", "capital", "liquidez"],
    "automation": ["automação", "repetitivo", "workflow", "eficiência"],
    "communication": ["comunicação", "mensagem", "linguagem", "relacionamento"],
    "evolution": ["evolução", "melhoria", "aprendizado", "resultado"],
}


class DiscoveryWorker:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        perception: PerceptionFabric | None = None,
    ) -> None:
        self.factory = factory
        self.perception = perception

    @staticmethod
    def _preferred_sensors(agent: Agent) -> list[str]:
        raw = (agent.capabilities_json or {}).get("preferred_sensors", [])
        if not isinstance(raw, list):
            return []
        return [str(item) for item in raw if isinstance(item, str) and item.strip()]

    @staticmethod
    def _exploration_enabled(agent: Agent) -> bool:
        strategy = (agent.capabilities_json or {}).get("exploration_strategy", {})
        return isinstance(strategy, dict) and strategy.get("mode") == "cross_sector"

    async def run_once(self, creator_id: str) -> dict[str, int]:
        checked = 0
        discovered = 0
        sensor_observations = 0

        async with self.factory() as session:
            universes = list(
                await session.scalars(
                    select(Universe).where(
                        Universe.active.is_(True),
                        Universe.code.in_(list(KEYWORDS)),
                    )
                )
            )

        for universe in universes:
            async with self.factory() as session:
                agent = await session.scalar(
                    select(Agent)
                    .where(Agent.universe_id == universe.id, Agent.active.is_(True))
                    .limit(1)
                )
                if agent is None:
                    continue

                checked += 1
                query = " ".join(KEYWORDS[universe.code])
                # Serialize research per Creator/Universe, not across the whole OS.
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                    {"key": "discovery:" + creator_id + ":" + universe.code},
                )
                result = await KnowledgeService(session).search(Scope(creator_id=creator_id), query)
                repo = DomainRepository(session)

                for evidence in result.evidences:
                    gap = "Investigar sinal em " + evidence.title + ": " + evidence.content[:600]
                    mechanism = "Pesquisa e validação de hipótese pelo Universo " + universe.name
                    window = {"knowledge_revision_id": evidence.revision_id}
                    fingerprint = normalize_opportunity_fingerprint(
                        sector=universe.code,
                        problem_or_gap=gap,
                        capture_mechanism=mechanism,
                        time_window=window,
                    )
                    exists = await session.scalar(
                        select(Opportunity.id).where(
                            Opportunity.creator_id == creator_id,
                            Opportunity.fingerprint == fingerprint,
                        )
                    )
                    if exists:
                        continue
                    await create_or_get_opportunity(
                        repo,
                        creator_id=creator_id,
                        discovered_by_universe_id=universe.id,
                        sector=universe.code,
                        problem_or_gap=gap,
                        capture_mechanism=mechanism,
                        evidence_refs=["knowledge:" + evidence.item_id + ":" + evidence.revision_id],
                        time_window=window,
                        correlation_id=str(uuid.uuid4()),
                    )
                    discovered += 1

                if self.perception is not None:
                    observations = await self.perception.observe(
                        creator_id=creator_id,
                        universe_code=universe.code,
                        preferred_sensors=self._preferred_sensors(agent),
                        query=query,
                        explore=self._exploration_enabled(agent),
                    )
                    sensor_observations += len(observations)
                    for observation in observations:
                        payload = json.dumps(
                            observation.data,
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                            default=str,
                        )
                        evidence_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
                        gap = (
                            "Investigar sinal multissensor "
                            + observation.sensor
                            + ": "
                            + payload[:600]
                        )
                        mechanism = "Percepção multissensor pelo Universo " + universe.name
                        window = {
                            "sensor": observation.sensor,
                            "evidence_hash": evidence_hash,
                        }
                        fingerprint = normalize_opportunity_fingerprint(
                            sector=universe.code,
                            problem_or_gap=gap,
                            capture_mechanism=mechanism,
                            time_window=window,
                        )
                        exists = await session.scalar(
                            select(Opportunity.id).where(
                                Opportunity.creator_id == creator_id,
                                Opportunity.fingerprint == fingerprint,
                            )
                        )
                        if exists:
                            continue
                        await create_or_get_opportunity(
                            repo,
                            creator_id=creator_id,
                            discovered_by_universe_id=universe.id,
                            sector=universe.code,
                            problem_or_gap=gap,
                            capture_mechanism=mechanism,
                            evidence_refs=[
                                "sensor:" + observation.sensor + ":" + evidence_hash
                            ],
                            time_window=window,
                            correlation_id=str(uuid.uuid4()),
                        )
                        discovered += 1

                await session.commit()

        return {
            "universes_checked": checked,
            "discoveries": discovered,
            "sensor_observations": sensor_observations,
        }


async def run() -> None:
    if not settings.deus_autonomy_discovery_enabled:
        logger.info("autonomous discovery disabled by configuration")
        return

    # Reuse the same centrally governed capability construction as Mission execution.
    # Import lazily to keep the discovery module independent from the task-worker startup.
    from app.worker import build_capability_gateway, register_mcp_capabilities

    gateway = build_capability_gateway()
    await register_mcp_capabilities(gateway)
    perception = build_perception_fabric(
        gateway,
        bindings_json=settings.perception_sensor_bindings_json,
        allowlist=settings.perception_sensor_allowlist,
        max_sensors_per_cycle=settings.perception_max_sensors_per_cycle,
    )
    worker = DiscoveryWorker(AsyncSessionLocal, perception=perception)
    while True:
        try:
            creator_id = await creator_scope()
            if creator_id:
                report = await worker.run_once(creator_id)
                logger.bind(**report).info("autonomous evidence research cycle")
        except Exception as exc:
            logger.bind(
                component="discovery",
                error_type=type(exc).__name__,
            ).warning("discovery cycle unavailable")
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(supervised("discovery-worker", run))
