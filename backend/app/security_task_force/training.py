from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from app.config import settings
from app.core.domain import Actor
from app.models.entities import Agent, Universe
from app.models.security_task_force import StfRun
from app.security_task_force.contracts import ActionRequest, MissionContract, RiskClass
from app.security_task_force.mission_compiler import CompilationResult, compile_verified_contract
from app.security_task_force.repository import StfRepository
from app.security_task_force.service import StfService

RANGE_ENVIRONMENT_ID = "cyber_range:lab-a"
ADVANCED_CAMPAIGN_ID = "stf-advanced-v1"
TRAINING_ACTION_CLASS = "range.training"


@dataclass(frozen=True)
class TrainingAgentSpec:
    code: str
    name: str
    cell: str
    specialty: str


TRAINING_AGENT_SPECS: tuple[TrainingAgentSpec, ...] = (
    TrainingAgentSpec("stf-range-commander", "STF Range Commander", "command", "mission_command"),
    TrainingAgentSpec("stf-red-recon", "STF Red Recon", "red", "reconnaissance"),
    TrainingAgentSpec("stf-red-appsec", "STF Red AppSec", "red", "application_security"),
    TrainingAgentSpec("stf-red-identity", "STF Red Identity", "red", "identity_authorization"),
    TrainingAgentSpec("stf-blue-detection", "STF Blue Detection", "blue", "detection_engineering"),
    TrainingAgentSpec("stf-blue-response", "STF Blue Response", "blue", "incident_response"),
    TrainingAgentSpec("stf-purple-validation", "STF Purple Validation", "purple", "control_validation"),
    TrainingAgentSpec("stf-forensics", "STF Forensics", "forensics", "digital_forensics"),
    TrainingAgentSpec("stf-cloud-container", "STF Cloud Container", "red-blue", "cloud_container_security"),
    TrainingAgentSpec("stf-supply-chain", "STF Supply Chain", "red-blue", "software_supply_chain"),
)


@dataclass(frozen=True)
class TrainingHistory:
    cycles: int = 0
    last_started_at: datetime | None = None


def training_mission_id(agent_code: str, *, creator_id: str | None = None, cycle: int | None = None) -> str:
    base = f"stf-training:{agent_code}"
    if cycle is None:
        return base
    if cycle < 1 or not creator_id:
        raise ValueError('A cycle requires a positive number and Creator scope')
    return f"{base}:{creator_id}:cycle-{cycle}"


def training_run_filter() -> ColumnElement[bool]:
    """Recognize historical shared missions and new per-Creator, per-cycle authority."""
    bases = [training_mission_id(spec.code) for spec in TRAINING_AGENT_SPECS]
    return or_(StfRun.mission_id.in_(bases), *[StfRun.mission_id.like(f'{base}:%') for base in bases])


def compile_training_contract(
    creator_id: str,
    spec: TrainingAgentSpec,
    *,
    environment_id: str = RANGE_ENVIRONMENT_ID,
    campaign_id: str = ADVANCED_CAMPAIGN_ID,
    cycle: int | None = None,
) -> CompilationResult:
    if not environment_id.startswith("cyber_range:"):
        raise ValueError("automatic STF training is restricted to cyber_range:*")
    if campaign_id != ADVANCED_CAMPAIGN_ID:
        raise ValueError("automatic STF training uses only the trusted advanced campaign")
    return compile_verified_contract(
        intent=f"Train {spec.name} in the isolated Cyber Range advanced campaign.",
        candidate={
            "mission_id": training_mission_id(spec.code, creator_id=creator_id, cycle=cycle),
            "creator_id": creator_id,
            "success_criteria": [
                "campaign lifecycle completed",
                "execution evidence preserved",
                "containment maintained",
            ],
            "excluded_targets": ["real:*"],
            "allowed_action_classes": [TRAINING_ACTION_CLASS],
            "risk_ceiling": RiskClass.R2.value,
            "resource_budget": {"max_parallel_runs": 1},
            "data_handling_class": "training_synthetic_only",
            "required_evidence": ["execution_evidence"],
            "rollback_requirements": ["range.reset"],
            "termination_conditions": [
                "containment_failure",
                "policy_bypass",
                "unknown_execution_outcome",
            ],
            "escalation_policy": {"real_environment": "deny"},
            "requested_specialties": [spec.specialty],
        },
        authorized_environments=[environment_id],
        authorized_targets=[campaign_id],
    )


def build_training_actions(
    contract: MissionContract,
    spec: TrainingAgentSpec,
    *,
    cycle: int,
) -> list[ActionRequest]:
    if cycle < 1:
        raise ValueError("training cycle must be positive")
    if contract.authorized_environments != [RANGE_ENVIRONMENT_ID]:
        raise ValueError("training contract must be bound to the canonical Cyber Range")
    if contract.authorized_targets != [ADVANCED_CAMPAIGN_ID]:
        raise ValueError("training contract must be bound to the trusted advanced campaign")

    sequence: tuple[tuple[str, RiskClass], ...] = (
        ("range.campaign.start", RiskClass.R2),
        ("range.campaign.advance", RiskClass.R2),
        ("range.campaign.advance", RiskClass.R2),
        ("range.campaign.advance", RiskClass.R2),
        ("range.campaign.verify", RiskClass.R1),
    )
    actions: list[ActionRequest] = []
    for index, (capability, risk) in enumerate(sequence, start=1):
        label = capability.rsplit(".", 1)[-1]
        actions.append(
            ActionRequest(
                action_id=f"{spec.code}:cycle-{cycle}:{index}-{label}",
                mission_id=contract.mission_id,
                mission_version=contract.mission_version,
                task_id=f"training:{spec.code}:cycle-{cycle}:{index}",
                actor=f"agent:{spec.code}",
                target_id=ADVANCED_CAMPAIGN_ID,
                environment_id=RANGE_ENVIRONMENT_ID,
                capability=capability,
                action_class=TRAINING_ACTION_CLASS,
                risk_class=risk,
                parameters={},
                rollback_reference="range.reset",
                evidence_expectation=["execution_evidence"],
                idempotency_key=f"stf-training:{spec.code}:{cycle}:{index}",
            )
        )
    return actions


def select_next_training_agent(
    specs: Sequence[TrainingAgentSpec],
    history: dict[str, TrainingHistory],
) -> TrainingAgentSpec:
    if not specs:
        raise ValueError("at least one training agent is required")

    def key(spec: TrainingAgentSpec) -> tuple[int, float, str]:
        item = history.get(spec.code, TrainingHistory())
        timestamp = item.last_started_at.timestamp() if item.last_started_at is not None else float("-inf")
        return item.cycles, timestamp, spec.code

    return min(specs, key=key)


def _training_capabilities(spec: TrainingAgentSpec) -> dict[str, object]:
    return {
        "inference_provider": settings.llm_provider,
        "training_profile": "stf-cyber-range-v1",
        "cell": spec.cell,
        "specialty": spec.specialty,
        "environment_scope": "cyber_range:*",
        "autonomous_training": True,
        "real_target_authority": False,
    }


async def ensure_training_agents(session: AsyncSession) -> list[Agent]:
    security = await session.scalar(select(Universe).where(Universe.code == "security"))
    if security is None or not security.active:
        raise RuntimeError("canonical security Universe must be active before STF training")

    codes = [item.code for item in TRAINING_AGENT_SPECS]
    existing = {
        item.code: item
        for item in (
            await session.scalars(select(Agent).where(Agent.code.in_(codes)).with_for_update())
        ).all()
    }
    ready: list[Agent] = []
    for spec in TRAINING_AGENT_SPECS:
        expected = _training_capabilities(spec)
        agent = existing.get(spec.code)
        if agent is None:
            agent = Agent(
                code=spec.code,
                name=spec.name,
                universe_id=security.id,
                active=True,
                capabilities_json=expected,
            )
            session.add(agent)
        else:
            agent.name = spec.name
            agent.universe_id = security.id
            agent.capabilities_json = expected
        ready.append(agent)
    await session.flush()
    return ready


class AutomaticRangeTraining:
    """Serial, fail-closed scheduler for the ten dedicated Cyber Range trainees.

    Only one training run is active at a time because the current Range campaign state is
    intentionally global. Completed/aborted runs are kept as immutable history; the agent with
    the fewest cycles and then the oldest start time is scheduled next.
    """

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory

    async def run_once(self, creator_id: str, *, agent_code: str | None = None) -> dict[str, object]:
        if agent_code is not None and agent_code not in {spec.code for spec in TRAINING_AGENT_SPECS}:
            raise ValueError("Unknown training agent")
        async with self.factory() as session:
            # The campaign has shared state; serialize manual requests and worker ticks.
            await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('creation:stf-training'))"))
            agents = await ensure_training_agents(session)
            available_codes = {agent.code for agent in agents if agent.active}
            if agent_code is not None and agent_code not in available_codes:
                raise ValueError("Training agent is paused")
            active = await session.scalar(
                select(StfRun)
                .where(
                    training_run_filter(),
                    StfRun.state.notin_(("COMPLETED", "ABORTED")),
                )
                .order_by(StfRun.created_at.asc())
                .limit(1)
            )
            if active is not None:
                await session.commit()
                result: dict[str, object] = {"status": "busy", "agents_ready": len(available_codes)}
                if active.creator_id == creator_id:
                    result.update(run_id=active.id, mission_id=active.mission_id)
                return result

            rows = (
                await session.execute(
                    select(
                        StfRun.mission_id,
                        func.count(StfRun.id),
                        func.max(StfRun.created_at),
                    )
                    .where(
                        StfRun.creator_id == creator_id,
                        training_run_filter(),
                    )
                    .group_by(StfRun.mission_id)
                )
            ).all()
            by_mission: dict[str, TrainingHistory] = {}
            for mission_id, cycles, last_started_at in rows:
                base = ':'.join(str(mission_id).split(':')[:2])
                previous = by_mission.get(base, TrainingHistory())
                dates = [date for date in (previous.last_started_at, last_started_at) if date is not None]
                by_mission[base] = TrainingHistory(cycles=previous.cycles + int(cycles),
                                                   last_started_at=max(dates) if dates else None)
            history = {
                spec.code: by_mission.get(training_mission_id(spec.code), TrainingHistory())
                for spec in TRAINING_AGENT_SPECS
            }
            if not available_codes:
                await session.commit()
                return {"status": "paused", "agents_ready": 0}
            eligible = [spec for spec in TRAINING_AGENT_SPECS if spec.code in available_codes]
            spec = next(spec for spec in eligible if spec.code == agent_code) if agent_code else select_next_training_agent(eligible, history)
            cycle = history[spec.code].cycles + 1

            repository = StfRepository(session)
            stored = await repository.get_contract(creator_id, training_mission_id(spec.code, creator_id=creator_id, cycle=cycle))
            if stored is None:
                compiled = compile_training_contract(creator_id, spec, cycle=cycle)
                if compiled.status != "COMPILED" or compiled.contract is None:
                    raise RuntimeError("automatic training contract compilation failed")
                await repository.save_contract(compiled)
                contract = compiled.contract
            else:
                contract = MissionContract.model_validate(stored.contract_json)

            service = StfService(session)
            view = await service.start(
                Actor(creator_id, "creator"),
                contract.mission_id,
                build_training_actions(contract, spec, cycle=cycle),
                request_key=f"auto-training:{spec.code}:cycle-{cycle}",
            )
            await session.commit()
            return {
                "status": "queued",
                "run_id": view.run_id,
                "mission_id": view.mission_id,
                "agent_code": spec.code,
                "cycle": cycle,
                "agents_ready": len(available_codes),
            }
