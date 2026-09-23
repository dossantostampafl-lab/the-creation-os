"""Give an empty system the Universes and Agents a Mission needs to be viable.

ROCKMAM assigns every Mission step to a Universe, and a plan is only viable when that
Universe is active and has an active Agent. On a fresh database there are none, so every
request comes back "not viable". This creates a working set, once.
"""

from __future__ import annotations

import asyncio
import json
import uuid

from sqlalchemy import select

from app.config import settings
from app.core.domain import Actor
from app.db.session import AsyncSessionLocal
from app.models.entities import Agent, Creator, Universe
from app.repositories.domain import DomainRepository
from app.services.domain import LivingCoreService

# Broad enough that ROCKMAM can place any first request, narrow enough to stay meaningful.
# Rename or add your own through /api/v1/universes once you know what you actually run.
UNIVERSES: tuple[tuple[str, str, str], ...] = (
    ("engineering", "Engineering", "Build, change and deploy software."),
    ("content", "Content", "Write, edit and publish text."),
    ("research", "Research", "Gather, read and summarize information."),
    ("operations", "Operations", "Run, watch and maintain what already exists."),
)


async def seed_universes() -> int:
    """Create each missing Universe, activate it, and staff it with one Agent."""
    async with AsyncSessionLocal() as session:
        creator = await session.scalar(select(Creator).limit(1))
        if creator is None:
            print(json.dumps({"seeded": False, "reason": "no_creator_yet"}))
            return 1
        if settings.sovereign_creator_id and settings.sovereign_creator_id != creator.id:
            print(json.dumps({"seeded": False, "reason": "creator_is_not_the_sovereign"}))
            return 1

        actor = Actor(creator.id, "creator")
        service = LivingCoreService(DomainRepository(session))
        created: list[str] = []
        activated: list[str] = []
        staffed: list[str] = []

        for code, name, description in UNIVERSES:
            universe = await session.scalar(select(Universe).where(Universe.code == code))
            if universe is None:
                universe = await service.create_universe(actor, code, name, str(uuid.uuid4()))
                created.append(code)
            if not universe.active:
                await service.set_universe_active(actor, universe.id, True, str(uuid.uuid4()))
                activated.append(code)

            agent_code = f"{code}-agent"
            agent = await session.scalar(select(Agent).where(Agent.code == agent_code))
            if agent is None:
                await service.create_agent(
                    actor,
                    agent_code,
                    f"{name} Agent",
                    universe.id,
                    # The runtime reads inference_provider to route the Agent's own calls;
                    # without it every task fails with "Agent has no inference_provider".
                    {"inference_provider": settings.llm_provider, "description": description},
                    str(uuid.uuid4()),
                )
                staffed.append(agent_code)
            elif not agent.active:
                await service.set_agent_active(actor, agent.id, True, str(uuid.uuid4()))
                staffed.append(agent_code)

        print(json.dumps({
            "seeded": True,
            "universes_created": created,
            "universes_activated": activated,
            "agents_ready": staffed,
        }))
        return 0


def main() -> None:
    raise SystemExit(asyncio.run(seed_universes()))


if __name__ == "__main__":
    main()
