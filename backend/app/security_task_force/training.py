from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from app.security_task_force.contracts import ActionRequest, MissionContract, RiskClass
from app.security_task_force.mission_compiler import CompilationResult, compile_verified_contract

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
