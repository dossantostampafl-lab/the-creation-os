from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import actor, correlation_id
from app.core.domain import Actor
from app.db.session import get_session
from app.repositories.domain import DomainRepository
from app.security_task_force.contracts import ActionRequest
from app.security_task_force.integration import SecurityTaskForceAdapter, build_adapter
from app.security_task_force.policy import OpaClient
from app.security_task_force.repository import ContractConflict, IdempotencyConflict, StfRepository
from app.security_task_force.service import RunConflict, RunForbidden, StfService

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


class StartRunBody(BaseModel):
    actions: list[ActionRequest]


class ApprovalBody(BaseModel):
    run_id: str | None = None
    action_id: str = Field(min_length=1)
    decision: str = Field(pattern=r"^(approve|deny)$")


class CancelBody(BaseModel):
    run_id: str | None = None
    reason: str = Field(min_length=1, max_length=1000)


class EvidenceBody(BaseModel):
    execution_id: str = Field(min_length=1, max_length=64)
    scenario_id: str = Field(min_length=1, max_length=64)
    kind: str = Field(pattern=r"^(attack|defense)$")
    source: str = Field(min_length=1, max_length=128)
    acquired_at: str | None = Field(default=None, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


async def _chronicle(session: AsyncSession, a: Actor, cid: str, event: str, mission_id: str, payload: dict[str, Any]) -> None:
    repo = DomainRepository(session)
    await repo.add_event(event, AGGREGATE, mission_id, a.id, a.role, cid, payload)
    await repo.commit()


def _http(error: Exception) -> HTTPException:
    if isinstance(error, LookupError):
        return _not_found(error)
    if isinstance(error, RunForbidden):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error))
    if isinstance(error, (IdempotencyConflict, RunConflict)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


async def _require_run_id(service: StfService, a: Actor, mission_id: str, run_id: str | None) -> None:
    """A mission with live runs must name the run: a bare mission-level command could signal the wrong one."""
    if run_id is None and await service.active_run_ids(a, mission_id):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="run_id is required")


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
    try:
        await StfRepository(session).save_contract(result)
    except ContractConflict as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
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


@router.post("/{mission_id}/runs", status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    mission_id: str,
    body: StartRunBody,
    idempotency_key: str = Header(min_length=1, max_length=256, alias="Idempotency-Key"),
    a: Actor = Depends(actor),
    session: AsyncSession = Depends(get_session),
):
    service = StfService(session)
    try:
        view = await service.start(a, mission_id, body.actions, idempotency_key)
        await session.commit()  # 202 only after the run, its audit event and its start command are durable
    except (LookupError, ValueError, PermissionError, IdempotencyConflict, RunConflict) as error:
        await session.rollback()
        raise _http(error) from error
    return view.as_dict()


@router.get("/{mission_id}/runs/{run_id}")
async def get_run(mission_id: str, run_id: str, a: Actor = Depends(actor), session: AsyncSession = Depends(get_session)):
    try:
        return (await StfService(session).get(a, mission_id, run_id)).as_dict()
    except LookupError as error:
        raise _not_found(error) from error


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
    service = StfService(session)
    if body.run_id is not None:
        try:
            approval = await service.approve(a, body.run_id, body.action_id, body.decision)
            await session.commit()
        except (LookupError, ValueError, PermissionError, RunConflict) as error:
            await session.rollback()
            raise _http(error) from error
        return {"approval_id": approval.id, "run_id": body.run_id, "decision": approval.decision}
    await _require_run_id(service, a, mission_id, body.run_id)
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
    service = StfService(session)
    if body.run_id is not None:
        try:
            view = await service.cancel(a, body.run_id, body.reason)
            await session.commit()
        except (LookupError, ValueError, PermissionError) as error:
            await session.rollback()
            raise _http(error) from error
        return view.as_dict()
    await _require_run_id(service, a, mission_id, body.run_id)
    try:
        adapter.cancel_mission(a, mission_id, body.reason)
    except LookupError as error:
        raise _not_found(error) from error
    await _chronicle(session, a, cid, "stf_mission_cancelled", mission_id, {"mission_id": mission_id, "reason": body.reason})
    return {"mission_id": mission_id, "status": "ABORTED"}


@router.post("/{mission_id}/runs/{run_id}/evidence", status_code=status.HTTP_201_CREATED)
async def record_run_evidence(
    mission_id: str,
    run_id: str,
    body: EvidenceBody,
    a: Actor = Depends(actor),
    session: AsyncSession = Depends(get_session),
):
    service = StfService(session)
    try:
        record = await service.record_evidence(
            a,
            mission_id,
            run_id,
            body.execution_id,
            scenario_id=body.scenario_id,
            kind=body.kind,
            source=body.source,
            acquired_at=body.acquired_at,
            payload=body.payload,
        )
        await session.commit()
    except (LookupError, ValueError, PermissionError, IdempotencyConflict, RunConflict) as error:
        await session.rollback()
        raise _http(error) from error
    return record.chronicle_payload()


@router.get("/{mission_id}/runs/{run_id}/findings")
async def run_findings(
    mission_id: str,
    run_id: str,
    a: Actor = Depends(actor),
    session: AsyncSession = Depends(get_session),
):
    try:
        return {"findings": await StfService(session).findings(a, mission_id, run_id)}
    except LookupError as error:
        raise _not_found(error) from error


@router.post("/{mission_id}/runs/{run_id}/qualification/finalize")
async def finalize_run_qualification(
    mission_id: str,
    run_id: str,
    a: Actor = Depends(actor),
    session: AsyncSession = Depends(get_session),
):
    service = StfService(session)
    try:
        result = await service.finalize_qualification(a, mission_id, run_id)
        await session.commit()
    except (LookupError, ValueError, PermissionError, RunConflict) as error:
        await session.rollback()
        raise _http(error) from error
    return result


@router.get("/{mission_id}/runs/{run_id}/qualification")
async def run_qualification(
    mission_id: str,
    run_id: str,
    a: Actor = Depends(actor),
    session: AsyncSession = Depends(get_session),
):
    try:
        result = await StfService(session).qualification(a, mission_id, run_id)
    except LookupError as error:
        raise _not_found(error) from error
    if result is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="qualification is not finalized")
    return result


@router.get("/{mission_id}/findings")
async def verified_findings(mission_id: str, a: Actor = Depends(actor), adapter: SecurityTaskForceAdapter = Depends(get_adapter)):
    try:
        return {"findings": adapter.get_verified_findings(a, mission_id)}
    except LookupError as error:
        raise _not_found(error) from error
