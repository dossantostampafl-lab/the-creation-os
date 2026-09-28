from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from .canonicalize import canonical_hash
from .contracts import MissionContract

POLICY_VERSION = "stf-v1"
COMPILER_VERSION = "1"


@dataclass(frozen=True)
class CompilationResult:
    status: str  # COMPILED | REJECTED
    reason_codes: list[str] = field(default_factory=list)
    contract: MissionContract | None = None
    contract_hash: str | None = None
    policy_version: str = POLICY_VERSION
    compiler_version: str = COMPILER_VERSION

    def record(self) -> dict[str, Any]:
        """What gets persisted next to the contract so anyone can re-verify it later."""
        if self.contract is None or self.contract_hash is None:
            raise ValueError("a rejected compilation has no record")
        return {
            "contract": self.contract.normalized_payload(),
            "contract_hash": self.contract_hash,
            "policy_version": self.policy_version,
            "compiler_version": self.compiler_version,
        }


def _rejected(*codes: str) -> CompilationResult:
    return CompilationResult(status="REJECTED", reason_codes=list(codes))


def compile_verified_contract(
    *,
    intent: str,
    candidate: Mapping[str, Any] | None = None,
    authorized_environments: list[str] | None = None,
    authorized_targets: list[str] | None = None,
) -> CompilationResult:
    """Turn a candidate produced by reasoning into a contract that can be verified, or refuse.

    The model's prose is never trusted or compared. What is kept is the schema-valid, policy-valid
    contract, normalized and hashed. Missing authority, target or environment is a rejection, never
    a default: silence is not authorization.
    """
    if not intent.strip():
        return _rejected("intent")
    data: dict[str, Any] = dict(candidate or {})
    if authorized_environments is not None:
        data["authorized_environments"] = authorized_environments
    if authorized_targets is not None:
        data["authorized_targets"] = authorized_targets
    data.setdefault("objective", intent.strip())

    reasons: list[str] = []
    if not data.get("authorized_environments"):
        reasons.append("environment")
    if not data.get("authorized_targets"):
        reasons.append("target")
    if not data.get("risk_ceiling"):
        reasons.append("risk_ceiling")
    if not data.get("allowed_action_classes"):
        reasons.append("action_class")
    if reasons:
        return _rejected(*reasons)

    try:
        contract = MissionContract.model_validate(data)
    except ValidationError as error:
        fields = sorted({str(item["loc"][0]) for item in error.errors() if item["loc"]})
        return _rejected("invalid_contract", *[f"field:{name}" for name in fields])
    return CompilationResult(
        status="COMPILED",
        contract=contract,
        contract_hash=canonical_hash(contract.normalized_payload()),
    )


def verify_compiled(contract_record: Mapping[str, Any]) -> bool:
    """Recompute the hash from the persisted contract; the model is not consulted."""
    try:
        contract = MissionContract.model_validate(contract_record["contract"])
    except (KeyError, ValidationError):
        return False
    return canonical_hash(contract.normalized_payload()) == contract_record.get("contract_hash")
