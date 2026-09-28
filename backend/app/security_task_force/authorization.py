from __future__ import annotations

from datetime import datetime, timezone

from .contracts import ActionRequest, AuthorizationDecision, MissionContract, RiskClass
from .grants import GrantStore
from .policy import PolicyClient, PolicyUnavailable

POLICY_VERSION = "stf-v1"


def evaluate_local(
    contract: MissionContract,
    action: ActionRequest,
    *,
    creator_approval_reference: str | None = None,
    now: datetime | None = None,
) -> tuple[str, list[str]]:
    """The Authorization Plane's own rules. The Rego policy mirrors them; both must agree to permit."""
    moment = now or datetime.now(timezone.utc)
    if action.mission_id != contract.mission_id or action.mission_version != contract.mission_version:
        return "deny", ["mission_version_mismatch"]
    if action.environment_id not in contract.authorized_environments:
        return "deny", ["environment_not_authorized"]
    if action.target_id not in contract.authorized_targets or action.target_id in contract.excluded_targets:
        return "deny", ["target_not_authorized"]
    if action.action_class not in contract.allowed_action_classes:
        return "deny", ["action_class_not_authorized"]
    window = contract.time_window
    if window and not (window["start"] <= moment < window["end"]):
        return "deny", ["outside_time_window"]
    if action.risk_class is RiskClass.R5:
        return "escalate", ["new_mission_required"]
    if action.risk_class.rank > contract.risk_ceiling.rank:
        return "escalate", ["risk_ceiling_exceeded"]
    if action.risk_class in (RiskClass.R3, RiskClass.R4) and not creator_approval_reference:
        return "escalate", ["creator_approval_required"]
    return "permit", []


def authorize(
    contract: MissionContract,
    action: ActionRequest,
    *,
    creator_approval_reference: str | None = None,
    now: datetime | None = None,
) -> AuthorizationDecision:
    decision, reasons = evaluate_local(contract, action, creator_approval_reference=creator_approval_reference, now=now)
    return _decision(action, decision, reasons, creator_approval_reference)


def _decision(action: ActionRequest, decision: str, reasons: list[str], approval: str | None, *,
              grant_id: str | None = None, expires_at: datetime | None = None) -> AuthorizationDecision:
    return AuthorizationDecision(
        decision_id=f"decision:{action.action_id}",
        action_id=action.action_id,
        decision=decision,
        policy_version=POLICY_VERSION,
        environment_id=action.environment_id,
        capability_grant_reference=grant_id,
        expires_at=expires_at,
        reason_codes=reasons,
        creator_approval_reference=approval,
    )


async def authorize_and_grant(
    contract: MissionContract,
    action: ActionRequest,
    *,
    grants: GrantStore,
    policy: PolicyClient | None = None,
    creator_approval_reference: str | None = None,
    now: datetime | None = None,
) -> AuthorizationDecision:
    """Decide, and only on a permit from every layer issue the ephemeral grant.

    Any failure of the policy engine is a denial: unavailable policy never means allowed.
    """
    decision, reasons = evaluate_local(contract, action, creator_approval_reference=creator_approval_reference, now=now)
    if decision == "permit" and policy is not None:
        try:
            allowed, policy_reasons = await policy.evaluate(contract, action, creator_approval_reference)
        except PolicyUnavailable:
            return _decision(action, "deny", ["policy_unavailable"], creator_approval_reference)
        if not allowed:
            return _decision(action, "deny", policy_reasons or ["policy_denied"], creator_approval_reference)
    if decision != "permit":
        return _decision(action, decision, reasons, creator_approval_reference)
    window_end = contract.time_window.get("end") if contract.time_window else None
    grant = grants.issue(action, not_after=window_end, now=now)
    return _decision(action, "permit", [], creator_approval_reference, grant_id=grant.grant_id, expires_at=grant.expires_at)
