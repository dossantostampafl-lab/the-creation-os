from __future__ import annotations

import hashlib
import hmac
from typing import Any

from .canonicalize import canonical_json
from .contracts import ActionRequest, AuthorizationDecision, CapabilityGrant

_INITIAL_CAPABILITY = "range.health.verify"
_INITIAL_PARAMETER_KEYS = {"path"}


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_float(item) for item in value)
    return False


def canonical_runtime_args(action: ActionRequest) -> str:
    """Canonical effective arguments for the only executable STF capability.

    Protocol v2 intentionally rejects floats and unknown keys so Python and Rust cannot disagree about
    the meaning of the bytes that are hashed and authorized.
    """
    if action.capability != _INITIAL_CAPABILITY:
        raise ValueError("only the initial capability has a canonical runtime schema")
    if set(action.parameters) - _INITIAL_PARAMETER_KEYS or _contains_float(action.parameters):
        raise ValueError("parameters are not canonical for range.health.verify")
    path = action.parameters.get("path", "/")
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("parameters are not canonical for range.health.verify")
    return canonical_json(action.parameters).decode("utf-8")


def parameters_hash(parameters: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(parameters)).hexdigest()


def signing_message(fields: dict[str, Any]) -> str:
    """Field order is the wire contract with the Rust gateway (security_gateway/src/signature.rs)."""
    order = (
        "protocol_version", "run_id", "execution_id", "contract_hash", "plan_hash",
        "mission_id", "mission_version", "action_id", "actor", "target", "environment",
        "capability", "action_class", "risk_class", "decision", "decision_id", "grant_id",
        "expires_unix", "nonce", "parameters_hash", "tool_id",
    )
    return "|".join(str(fields[name]) for name in order)


def build_envelope(
    action: ActionRequest,
    decision: AuthorizationDecision,
    grant: CapabilityGrant,
    *,
    key: bytes,
    nonce: str,
    run_id: str = "",
    execution_id: str = "",
    contract_hash: str = "",
    plan_hash: str = "",
    tool_id: str = "",
) -> dict[str, Any]:
    if decision.decision != "permit" or decision.capability_grant_reference != grant.grant_id:
        raise ValueError("an envelope needs a permit that names this grant")
    if decision.environment_id != action.environment_id or grant.environment_id != action.environment_id:
        raise ValueError("environment differs across action, decision and grant")
    canonical_runtime_args(action)
    runtime_bound = all((run_id, execution_id, contract_hash, plan_hash, tool_id))
    fields: dict[str, Any] = {
        "protocol_version": 2 if runtime_bound else 1,
        "run_id": run_id,
        "execution_id": execution_id,
        "contract_hash": contract_hash,
        "plan_hash": plan_hash,
        "mission_id": action.mission_id,
        "mission_version": action.mission_version,
        "action_id": action.action_id,
        "actor": action.actor,
        "target": action.target_id,
        "environment": action.environment_id,
        "capability": action.capability,
        "action_class": action.action_class,
        "risk_class": action.risk_class.value,
        "decision": decision.decision,
        "decision_id": decision.decision_id,
        "grant_id": grant.grant_id,
        "expires_unix": int(grant.expires_at.timestamp()),
        "nonce": nonce,
        "parameters_hash": parameters_hash(action.parameters),
        "tool_id": tool_id or action.capability,
    }
    signature = hmac.new(key, signing_message(fields).encode(), hashlib.sha256).hexdigest()
    return {**fields, "signature": signature}
