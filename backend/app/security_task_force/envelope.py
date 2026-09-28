from __future__ import annotations

import hashlib
import hmac
from typing import Any

from .canonicalize import canonical_json
from .contracts import ActionRequest, AuthorizationDecision, CapabilityGrant


def parameters_hash(parameters: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(parameters)).hexdigest()


def signing_message(fields: dict[str, Any]) -> str:
    """Field order is the wire contract with the Rust gateway (security_gateway/src/signature.rs)."""
    order = ("mission_id", "mission_version", "action_id", "actor", "target", "environment", "capability",
             "action_class", "risk_class", "decision", "decision_id", "grant_id", "expires_unix", "parameters_hash")
    return "|".join(str(fields[name]) for name in order)


def build_envelope(action: ActionRequest, decision: AuthorizationDecision, grant: CapabilityGrant, *, key: bytes,
                   nonce: str) -> dict[str, Any]:
    if decision.decision != "permit" or decision.capability_grant_reference != grant.grant_id:
        raise ValueError("an envelope needs a permit that names this grant")
    if decision.environment_id != action.environment_id or grant.environment_id != action.environment_id:
        raise ValueError("environment differs across action, decision and grant")
    fields: dict[str, Any] = {
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
        "parameters_hash": parameters_hash(action.parameters),
    }
    signature = hmac.new(key, signing_message(fields).encode(), hashlib.sha256).hexdigest()
    return {**fields, "nonce": nonce, "signature": signature}
