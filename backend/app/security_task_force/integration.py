from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.domain import Actor, AuthorizationDenied, require_creator

from .authorization import authorize_and_grant
from .contract_store import ContractStore
from .contracts import ActionRequest, AuthorizationDecision, MissionContract
from .grants import GrantStore
from .kill_switch import KillSwitch
from .mission_compiler import CompilationResult, compile_verified_contract
from .policy import PolicyClient
from .status_store import MissionStatusStore


@dataclass(frozen=True)
class MissionStatusView:
    mission_id: str
    status: str
    contract_hash: str | None = None


class SecurityTaskForceAdapter:
    """The only door between THE CREATION OS and the Task Force.

    It can compile a Mission, ask the Authorization Plane about an action, read status and verified
    findings, take the Creator's approval and cancel. It holds no repository, session, gateway or
    executor handle, so nothing reachable from here dispatches privileged work: dispatch happens only
    in the workflow, after authorization, through the gateway."""

    def __init__(self, *, contracts: ContractStore, grants: GrantStore, kill_switch: KillSwitch,
                 statuses: MissionStatusStore, policy: PolicyClient | None = None) -> None:
        self.__contracts = contracts
        self.__grants = grants
        self.__kill_switch = kill_switch
        self.__statuses = statuses
        self.__policy = policy

    def _owned_contract(self, creator: Actor, mission_id: str) -> MissionContract:
        require_creator(creator, "use the Security Task Force")
        contract = self.__contracts.get(mission_id)
        if contract is None or contract.creator_id != creator.id:
            raise LookupError("Mission not found")
        return contract

    def compile_mission(self, creator: Actor, intent: str, candidate: Mapping[str, Any] | None = None, *,
                        authorized_environments: list[str] | None = None,
                        authorized_targets: list[str] | None = None) -> CompilationResult:
        require_creator(creator, "compile a Security Task Force Mission")
        # The Creator identity comes from the session, never from the candidate the model produced.
        data = {**(candidate or {}), "creator_id": creator.id}
        result = compile_verified_contract(intent=intent, candidate=data, authorized_environments=authorized_environments,
                                           authorized_targets=authorized_targets)
        if result.status == "COMPILED":
            assert result.contract is not None
            existing = self.__contracts.get(result.contract.mission_id)
            if existing is not None and existing.creator_id != creator.id:
                raise AuthorizationDenied("Mission id belongs to another Creator")
            self.__contracts.put(result)
            self.__statuses.set_state(result.contract.mission_id, "COMPILED")
        return result

    async def request_authorization(self, creator: Actor, mission_id: str, action: Mapping[str, Any],
                                    creator_approval_reference: str | None = None) -> AuthorizationDecision:
        contract = self._owned_contract(creator, mission_id)
        request = ActionRequest.model_validate(dict(action))
        if not self.__kill_switch.dispatch_allowed(mission_id):
            return AuthorizationDecision(decision_id=f"decision:{request.action_id}", action_id=request.action_id,
                                         decision="deny", policy_version="stf-v1", reason_codes=["kill_switch"])
        return await authorize_and_grant(contract, request, grants=self.__grants, policy=self.__policy,
                                         creator_approval_reference=creator_approval_reference)

    def get_mission_status(self, creator: Actor, mission_id: str) -> MissionStatusView:
        self._owned_contract(creator, mission_id)
        record = self.__contracts.record(mission_id) or {}
        state = self.__statuses.state(mission_id) or "UNKNOWN"
        if not self.__kill_switch.dispatch_allowed(mission_id) and state not in {"COMPLETED", "ABORTED"}:
            state = "ABORTED"
        return MissionStatusView(mission_id=mission_id, status=state, contract_hash=record.get("contract_hash"))

    def submit_creator_approval(self, creator: Actor, mission_id: str, action_id: str, decision: str) -> str | None:
        """An approval reference for one action of one of the Creator's own Missions, or None on deny."""
        self._owned_contract(creator, mission_id)
        if decision not in {"approve", "deny"}:
            raise ValueError("invalid creator decision")
        return f"creator-approval:{creator.id}:{mission_id}:{action_id}" if decision == "approve" else None

    def cancel_mission(self, creator: Actor, mission_id: str, reason: str) -> None:
        self._owned_contract(creator, mission_id)
        if not reason.strip():
            raise ValueError("cancellation reason is required")
        self.__kill_switch.kill_mission(mission_id)
        self.__grants.revoke_mission(mission_id)
        self.__statuses.set_state(mission_id, "ABORTED")

    def get_verified_findings(self, creator: Actor, mission_id: str) -> list[dict[str, Any]]:
        self._owned_contract(creator, mission_id)
        return self.__statuses.findings(mission_id, status="confirmed")


def build_adapter(state_dir: Path, policy: PolicyClient | None = None) -> SecurityTaskForceAdapter:
    """The adapter over the state the Task Force worker shares (same directory, same files)."""
    return SecurityTaskForceAdapter(
        contracts=ContractStore(state_dir / "contracts.json"), grants=GrantStore(state_dir / "grants.json"),
        kill_switch=KillSwitch(state_dir / "kill.json"), statuses=MissionStatusStore(state_dir / "status.json"),
        policy=policy,
    )
