from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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


def training_mission_id(agent_code: str) -> str:
    return f"stf-training:{agent_code}"


def compile_training_contract(
    creator_id: str,
    spec: TrainingAgentSpec,
    *,
    environment_id: str = RANGE_ENVIRONMENT_ID,
    campaign_id: str = ADVANCED_CAMPAIGN_ID,
) -> CompilationResult:
    if not environment_id.startswith("cyber_range:"):
        raise ValueError("automatic STF training is restricted to cyber_range:*")
    if campaign_id != ADVANCED_CAMPAIGN_ID:
        raise ValueError("automatic STF training uses only the trusted advanced campaign")
    return compile_verified_contract(
        intent=f"Train {spec.name} in the isolated Cyber Range advanced campaign.",
        candidate={
            "mission_id": training_mission_id(spec.code),
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
            await session.scalars(select(Agent).where(Agent.code.in_(codes)))
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
            agent.active = True
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

    async def run_once(self, creator_id: str) -> dict[str, object]:
        mission_ids = [training_mission_id(item.code) for item in TRAINING_AGENT_SPECS]
        async with self.factory() as session:
            agents = await ensure_training_agents(session)
            active = await session.scalar(
                select(StfRun)
                .where(
                    StfRun.creator_id == creator_id,
                    StfRun.mission_id.in_(mission_ids),
                    StfRun.state.notin_(("COMPLETED", "ABORTED")),
                )
                .order_by(StfRun.created_at.asc())
                .limit(1)
            )
            if active is not None:
                await session.commit()
                return {
                    "status": "busy",
                    "run_id": active.id,
                    "mission_id": active.mission_id,
                    "agents_ready": len(agents),
                }

            rows = (
                await session.execute(
                    select(
                        StfRun.mission_id,
                        func.count(StfRun.id),
                        func.max(StfRun.created_at),
                    )
                    .where(
                        StfRun.creator_id == creator_id,
                        StfRun.mission_id.in_(mission_ids),
                    )
                    .group_by(StfRun.mission_id)
                )
            ).all()
            by_mission = {
                str(mission_id): TrainingHistory(
                    cycles=int(cycles),
                    last_started_at=last_started_at,
                )
                for mission_id, cycles, last_started_at in rows
            }
            history = {
                spec.code: by_mission.get(training_mission_id(spec.code), TrainingHistory())
                for spec in TRAINING_AGENT_SPECS
            }
            spec = select_next_training_agent(TRAINING_AGENT_SPECS, history)
            cycle = history[spec.code].cycles + 1

            repository = StfRepository(session)
            stored = await repository.get_contract(creator_id, training_mission_id(spec.code))
            if stored is None:
                compiled = compile_training_contract(creator_id, spec)
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
                "agents_ready": len(agents),
            }
