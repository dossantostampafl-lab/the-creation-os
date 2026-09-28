from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import actor, correlation_id
from app.core.domain import Actor
from app.db.session import get_session
from app.repositories.domain import DomainRepository
from app.security_task_force.integration import SecurityTaskForceAdapter, build_adapter
from app.security_task_force.policy import OpaClient

# Mission initiation is an explicit, authenticated path. It never runs inside normal DEUS conversation.
router = APIRouter(prefix="/deus/security-missions", tags=["security-task-force"])

AGGREGATE = "stf_mission"


def get_adapter() -> SecurityTaskForceAdapter:
    opa_url = os.environ.get("OPA_URL")
    if os.environ.get("STF_REQUIRE_POLICY") == "1" and not opa_url:
        # An installation that demands the external policy engine never falls back to local rules alone.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Policy engine is required but not configured")
    return build_adapter(Path(os.environ.get("STF_STATE_DIR", "/var/lib/creation/stf")), OpaClient(opa_url) if opa_url else None)


class CompileRequest(BaseModel):
    intent: str = Field(min_length=3, max_length=8000)
    candidate: dict[str, Any] = Field(default_factory=dict)
    authorized_environments: list[str] = Field(default_factory=list)
    authorized_targets: list[str] = Field(default_factory=list)


class ActionBody(BaseModel):
    action: dict[str, Any]
    creator_approval_reference: str | None = None


class ApprovalBody(BaseModel):
    action_id: str = Field(min_length=1)
    decision: str = Field(pattern=r"^(approve|deny)$")


class CancelBody(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


async def _chronicle(session: AsyncSession, a: Actor, cid: str, event: str, mission_id: str, payload: dict[str, Any]) -> None:
    repo = DomainRepository(session)
    await repo.add_event(event, AGGREGATE, mission_id, a.id, a.role, cid, payload)
    await repo.commit()


def _not_found(error: LookupError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


@router.post("/compile", status_code=status.HTTP_201_CREATED)
async def compile_mission(
    body: CompileRequest,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    adapter: SecurityTaskForceAdapter = Depends(get_adapter),
    session: AsyncSession = Depends(get_session),
):
    result = adapter.compile_mission(a, body.intent, body.candidate, authorized_environments=body.authorized_environments,
                                     authorized_targets=body.authorized_targets)
    if result.status != "COMPILED" or result.contract is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"status": result.status, "reason_codes": result.reason_codes})
    await _chronicle(session, a, cid, "stf_mission_compiled", result.contract.mission_id, {
        "mission_id": result.contract.mission_id, "contract_hash": result.contract_hash,
        "environment_ids": result.contract.authorized_environments, "policy_version": result.policy_version,
    })
    return {"mission_id": result.contract.mission_id, "status": result.status, "contract_hash": result.contract_hash,
            "authorized_environments": result.contract.authorized_environments}


@router.post("/{mission_id}/authorize")
async def authorize_action(
    mission_id: str,
    body: ActionBody,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    adapter: SecurityTaskForceAdapter = Depends(get_adapter),
    session: AsyncSession = Depends(get_session),
):
    try:
        decision = await adapter.request_authorization(a, mission_id, body.action, body.creator_approval_reference)
    except LookupError as error:
        raise _not_found(error) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    await _chronicle(session, a, cid, "stf_action_decided", mission_id, {
        "mission_id": mission_id, "action_id": decision.action_id, "decision": decision.decision,
        "environment_id": decision.environment_id, "reason_codes": decision.reason_codes,
        "grant_id": decision.capability_grant_reference,
    })
    return decision.model_dump(mode="json")


@router.get("/{mission_id}")
async def mission_status(mission_id: str, a: Actor = Depends(actor), adapter: SecurityTaskForceAdapter = Depends(get_adapter)):
    try:
        view = adapter.get_mission_status(a, mission_id)
    except LookupError as error:
        raise _not_found(error) from error
    return {"mission_id": view.mission_id, "status": view.status, "contract_hash": view.contract_hash}


@router.post("/{mission_id}/approval")
async def creator_approval(
    mission_id: str,
    body: ApprovalBody,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    adapter: SecurityTaskForceAdapter = Depends(get_adapter),
    session: AsyncSession = Depends(get_session),
):
    try:
        reference = adapter.submit_creator_approval(a, mission_id, body.action_id, body.decision)
    except LookupError as error:
        raise _not_found(error) from error
    await _chronicle(session, a, cid, "stf_creator_decision", mission_id,
                     {"mission_id": mission_id, "action_id": body.action_id, "decision": body.decision})
    return {"creator_approval_reference": reference}


@router.post("/{mission_id}/cancel")
async def cancel_mission(
    mission_id: str,
    body: CancelBody,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    adapter: SecurityTaskForceAdapter = Depends(get_adapter),
    session: AsyncSession = Depends(get_session),
):
    try:
        adapter.cancel_mission(a, mission_id, body.reason)
    except LookupError as error:
        raise _not_found(error) from error
    await _chronicle(session, a, cid, "stf_mission_cancelled", mission_id, {"mission_id": mission_id, "reason": body.reason})
    return {"mission_id": mission_id, "status": "ABORTED"}


@router.get("/{mission_id}/findings")
async def verified_findings(mission_id: str, a: Actor = Depends(actor), adapter: SecurityTaskForceAdapter = Depends(get_adapter)):
    try:
        return {"findings": adapter.get_verified_findings(a, mission_id)}
    except LookupError as error:
        raise _not_found(error) from error
