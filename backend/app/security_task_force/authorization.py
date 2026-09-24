from __future__ import annotations

from .contracts import (\n    ActionRequest,\n    AuthorizationDecision,\n    MissionContract,\n    RiskClass,\n)


_RISK = {RiskClass.R0: 0, RiskClass.R1: 1, RiskClass.R2: 2, RiskClass.R3: 3, RiskClass.R4: 4, RiskClass.R5: 5}


def authorize(contract: MissionContract, action: ActionRequest, *, creator_approval_reference: str | None = None) -> AuthorizationDecision:
    reasons: list[str] = []
    decision = "permit"
    if action.mission_id != contract.mission_id or action.mission_version != contract.mission_version:
        decision, reasons = "deny", ["mission_version_mismatch"]
    elif action.environment not in contract.authorized_environments:
        decision, reasons = "deny", ["environment_not_authorized"]
    elif action.target_id not in contract.authorized_targets or action.target_id in contract.excluded_targets:
        decision, reasons = "deny", ["target_not_authorized"]
    elif action.action_class not in contract.allowed_action_classes:
        decision, reasons = "deny", ["action_class_not_authorized"]
    elif _RISK[action.risk_class] > _RISK[contract.risk_ceiling]:
        decision, reasons = "escalate", ["risk_ceiling_exceeded"]
    elif action.risk_class is RiskClass.R5:
        decision, reasons = "escalate", ["new_mission_required"]
    elif action.risk_class in (RiskClass.R3, RiskClass.R4) and not creator_approval_reference:
        decision, reasons = "escalate", ["creator_approval_required"]
    return AuthorizationDecision(
        decision_id=f"decision:{action.action_id}",
        action_id=action.action_id,
        decision=decision,
        policy_version="stf-v1",
        creator_approval_reference=creator_approval_reference,
        reason_codes=reasons,
    )
