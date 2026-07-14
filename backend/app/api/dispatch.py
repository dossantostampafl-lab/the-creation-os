import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.core.dispatch_state_machine import DispatchState
from app.db.session import get_session
from app.repositories.dispatch import DispatchRepository
from app.repositories.tree_core import TreeCoreRepository
from app.schemas.auth import TokenPayload
from app.schemas.dispatch import Attempt, Enqueue, Failure, Item, Lease, LeaseCommand, Leased
from app.services.dispatch import DispatchService
from app.services.tree_core import TreeCoreService

router = APIRouter(prefix="/dispatch", tags=["dispatch"], dependencies=[Depends(get_sovereign_creator)])


def service(session: AsyncSession = Depends(get_session)):
    return DispatchService(DispatchRepository(session), TreeCoreService(TreeCoreRepository(session)))


def item(x):
    return Item(**{k: getattr(x, k) for k in Item.model_fields})


@router.post("", response_model=Item, status_code=status.HTTP_201_CREATED)
async def enqueue(body: Enqueue, actor: TokenPayload = Depends(get_sovereign_creator), s: DispatchService = Depends(service)):
    return item(await s.enqueue(actor.sub, str(body.task_id), body.priority, body.max_attempts))


@router.get("", response_model=list[Item])
async def listing(
    mission_id: uuid.UUID | None = None,
    state: DispatchState | None = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    s: DispatchService = Depends(service),
):
    return [item(x) for x in await s.repository.list(str(mission_id) if mission_id else None, state.value if state else None, limit, offset)]


@router.get("/{item_id}", response_model=Item)
async def get(item_id: uuid.UUID, s: DispatchService = Depends(service)):
    return item(await s.get(str(item_id)))


@router.post("/lease", response_model=Leased)
async def lease(body: Lease, s: DispatchService = Depends(service)):
    x, token = await s.lease(body.worker_id, body.lease_seconds)
    return Leased(item=item(x) if x else None, lease_token=token)


@router.post("/{item_id}/renew", response_model=Item)
async def renew(item_id: uuid.UUID, body: LeaseCommand, s: DispatchService = Depends(service)):
    return item(await s.renew(str(item_id), body.worker_id, body.lease_token, body.lease_seconds))


@router.post("/{item_id}/acknowledge", response_model=Item)
async def ack(item_id: uuid.UUID, body: LeaseCommand, s: DispatchService = Depends(service)):
    return item(await s.acknowledge(str(item_id), body.worker_id, body.lease_token))


@router.post("/{item_id}/fail", response_model=Item)
async def fail(item_id: uuid.UUID, body: Failure, s: DispatchService = Depends(service)):
    return item(await s.fail(str(item_id), body.worker_id, body.lease_token, body.error_code, body.error_message))


@router.post("/{item_id}/release", response_model=Item)
async def release(item_id: uuid.UUID, body: LeaseCommand, s: DispatchService = Depends(service)):
    return item(await s.release(str(item_id), body.worker_id, body.lease_token))


@router.post("/{item_id}/cancel", response_model=Item)
async def cancel(item_id: uuid.UUID, s: DispatchService = Depends(service)):
    return item(await s.cancel(str(item_id)))


@router.get("/{item_id}/attempts", response_model=list[Attempt])
async def attempts(item_id: uuid.UUID, s: DispatchService = Depends(service)):
    await s.get(str(item_id))
    return [Attempt(**{k: getattr(x, k) for k in Attempt.model_fields}) for x in await s.repository.attempts(str(item_id))]
