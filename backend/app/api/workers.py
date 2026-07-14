import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.db.session import get_session
from app.repositories.dispatch import DispatchRepository
from app.repositories.tree_core import TreeCoreRepository
from app.repositories.workers import WorkerRepository
from app.schemas.workers import (
    Claim,
    ExecutionEnvelope,
    FailAction,
    Heartbeat,
    LeaseAction,
    RegisteredWorker,
    RegisterWorker,
    WorkerView,
)
from app.services.dispatch import DispatchService
from app.services.tree_core import TreeCoreService
from app.services.workers import WorkerService

router = APIRouter(prefix="/workers", tags=["workers"])


def service(session: AsyncSession = Depends(get_session)):
    dispatch = DispatchService(DispatchRepository(session), TreeCoreService(TreeCoreRepository(session)))
    return WorkerService(WorkerRepository(session), dispatch)


def view(worker):
    return WorkerView(
        id=worker.id,
        worker_uuid=worker.worker_uuid,
        worker_name=worker.worker_name,
        version=worker.version,
        capabilities=sorted(x.name for x in worker.capabilities),
        status=worker.status,
        last_heartbeat=worker.last_heartbeat,
        registered_at=worker.registered_at,
        updated_at=worker.updated_at,
    )


async def authenticated_worker(
    x_worker_uuid: uuid.UUID | None = Header(None),
    x_worker_token: str | None = Header(None),
    s: WorkerService = Depends(service),
):
    if x_worker_uuid is None or not x_worker_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Worker credentials required")
    return await s.authenticate(str(x_worker_uuid), x_worker_token)


@router.post("/register", response_model=RegisteredWorker, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterWorker, _: object = Depends(get_sovereign_creator), s: WorkerService = Depends(service)):
    worker, token = await s.register(str(body.worker_uuid), body.worker_name, body.version, body.capabilities)
    return RegisteredWorker(**view(worker).model_dump(), worker_token=token)


@router.post("/heartbeat", response_model=WorkerView)
async def heartbeat(body: Heartbeat, worker=Depends(authenticated_worker), s: WorkerService = Depends(service)):
    return view(await s.heartbeat(worker, body.version, body.status))


@router.post("/claim", response_model=ExecutionEnvelope | None)
async def claim(body: Claim, worker=Depends(authenticated_worker), s: WorkerService = Depends(service)):
    result = await s.claim(worker, body.lease_seconds)
    if result is None:
        return None
    item, token, capability = result
    return ExecutionEnvelope(
        dispatch_id=item.id,
        mission_id=item.mission_id,
        task_id=item.task_id,
        agent_id=item.agent_id,
        capability=capability,
        priority=item.priority,
        lease_token=token,
        attempt=item.attempt_count,
        deadline=item.lease_expires_at,
        metadata={},
    )


@router.post("/release", response_model=WorkerView)
async def release(body: LeaseAction, worker=Depends(authenticated_worker), s: WorkerService = Depends(service)):
    await s.release(worker, str(body.dispatch_id), body.lease_token)
    return view(worker)


@router.post("/acknowledge", response_model=WorkerView)
async def acknowledge(body: LeaseAction, worker=Depends(authenticated_worker), s: WorkerService = Depends(service)):
    await s.acknowledge(worker, str(body.dispatch_id), body.lease_token)
    return view(worker)


@router.post("/fail", response_model=WorkerView)
async def fail(body: FailAction, worker=Depends(authenticated_worker), s: WorkerService = Depends(service)):
    await s.fail(worker, str(body.dispatch_id), body.lease_token, body.error_code, body.error_message)
    return view(worker)


@router.post("/shutdown", response_model=WorkerView)
async def shutdown(worker=Depends(authenticated_worker), s: WorkerService = Depends(service)):
    return view(await s.shutdown(worker))


@router.get("", response_model=list[WorkerView], dependencies=[Depends(get_sovereign_creator)])
async def listing(s: WorkerService = Depends(service)):
    return [view(x) for x in await s.repository.list()]


@router.get("/{worker_id}", response_model=WorkerView, dependencies=[Depends(get_sovereign_creator)])
async def get(worker_id: uuid.UUID, s: WorkerService = Depends(service)):
    return view(await s.get(str(worker_id)))
