import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.workers import authenticated_worker
from app.auth.dependencies import get_sovereign_creator
from app.db.session import get_session
from app.repositories.dispatch import DispatchRepository
from app.repositories.execution import ExecutionRepository
from app.repositories.tree_core import TreeCoreRepository
from app.schemas.execution import ExecutionCommand, ExecutionCreate, ExecutionEventView, ExecutionResultView, ExecutionView
from app.services.dispatch import DispatchService
from app.services.execution import AgentExecutionService
from app.services.tree_core import TreeCoreService

router = APIRouter(prefix="/agents/executions", tags=["agent-executions"])


def service(session: AsyncSession = Depends(get_session)):
    dispatch = DispatchService(DispatchRepository(session), TreeCoreService(TreeCoreRepository(session)))
    return AgentExecutionService(ExecutionRepository(session), dispatch)


def view(value):
    return ExecutionView(**{key: getattr(value, key) for key in ExecutionView.model_fields})


@router.post("", response_model=ExecutionView, status_code=status.HTTP_201_CREATED)
async def create(body: ExecutionCreate, worker=Depends(authenticated_worker), s: AgentExecutionService = Depends(service)):
    return view(await s.create(worker, str(body.dispatch_id), body.lease_token, body.handler_name, body.handler_version))


@router.get("", response_model=list[ExecutionView], dependencies=[Depends(get_sovereign_creator)])
async def listing(limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0), s: AgentExecutionService = Depends(service)):
    return [view(value) for value in await s.repository.list(limit, offset)]


@router.get("/{execution_id}", response_model=ExecutionView, dependencies=[Depends(get_sovereign_creator)])
async def get(execution_id: uuid.UUID, s: AgentExecutionService = Depends(service)):
    return view(await s.get(str(execution_id)))


@router.post("/{execution_id}/accept", response_model=ExecutionView)
async def accept(execution_id: uuid.UUID, body: ExecutionCommand, worker=Depends(authenticated_worker), s: AgentExecutionService = Depends(service)):
    return view(await s.accept(str(execution_id), worker, body.lease_token))


@router.post("/{execution_id}/run", response_model=ExecutionView)
async def run(execution_id: uuid.UUID, body: ExecutionCommand, worker=Depends(authenticated_worker), s: AgentExecutionService = Depends(service)):
    return view(await s.run(str(execution_id), worker, body.lease_token))


@router.post("/{execution_id}/cancel", response_model=ExecutionView)
async def cancel(execution_id: uuid.UUID, body: ExecutionCommand, worker=Depends(authenticated_worker), s: AgentExecutionService = Depends(service)):
    return view(await s.cancel(str(execution_id), worker, body.lease_token))


@router.get("/{execution_id}/events", response_model=list[ExecutionEventView], dependencies=[Depends(get_sovereign_creator)])
async def events(execution_id: uuid.UUID, s: AgentExecutionService = Depends(service)):
    await s.get(str(execution_id))
    return [ExecutionEventView(**{key: getattr(value, key) for key in ExecutionEventView.model_fields}) for value in await s.repository.events(str(execution_id))]


@router.get("/{execution_id}/result", response_model=ExecutionResultView, dependencies=[Depends(get_sovereign_creator)])
async def result(execution_id: uuid.UUID, s: AgentExecutionService = Depends(service)):
    value = await s.result(str(execution_id))
    return ExecutionResultView(
        execution_id=value.id,
        mission_id=value.mission_id,
        task_id=value.task_id,
        agent_id=value.agent_id,
        capability_id=value.capability_id,
        status=value.state,
        output=value.output_payload,
        metrics=value.result_metrics,
        warnings=value.result_warnings,
        error_code=value.error_code,
        started_at=value.started_at,
        finished_at=value.finished_at,
    )
