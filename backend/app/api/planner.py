import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.db.session import get_session
from app.repositories.planner import PlannerRepository
from app.schemas.auth import TokenPayload
from app.schemas.planner import DependencyCreate, GraphResponse, PlannerRequest, TaskCreate, TaskPatch, TaskResponse, TopologyResponse
from app.services.planner import PlannerService

router = APIRouter(tags=["mission-planner"])


def service(session: AsyncSession = Depends(get_session)):
    return PlannerService(PlannerRepository(session))


def response(item):
    return TaskResponse(
        id=item.id,
        mission_id=item.mission_id,
        parent_task_id=item.parent_task_id,
        name=item.name,
        description=item.description,
        required_capability=item.required_capability_id,
        priority=item.priority,
        state=item.state,
        retry_limit=item.retry_limit,
        retry_count=item.retry_count,
        timeout_seconds=item.timeout_seconds,
        estimated_duration=item.estimated_duration,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post("/tree-core/plan", response_model=list[TaskResponse], status_code=201)
async def plan(body: PlannerRequest, actor: TokenPayload = Depends(get_sovereign_creator), s: PlannerService = Depends(service)):
    return [response(x) for x in await s.plan(actor.sub, str(body.mission_id), str(body.required_capability))]


@router.get("/tasks", response_model=list[TaskResponse])
async def tasks(
    mission_id: uuid.UUID = Query(...), actor: TokenPayload = Depends(get_sovereign_creator), s: PlannerService = Depends(service)
):
    return [response(x) for x in await s.list(actor.sub, str(mission_id))]


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create(body: TaskCreate, actor: TokenPayload = Depends(get_sovereign_creator), s: PlannerService = Depends(service)):
    data = body.model_dump()
    data["mission_id"] = str(data["mission_id"])
    data["parent_task_id"] = str(data["parent_task_id"]) if data["parent_task_id"] else None
    data["required_capability_id"] = str(data.pop("required_capability"))
    data["retry_count"] = 0
    return response(await s.create_task(actor.sub, **data))


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get(task_id: uuid.UUID, actor: TokenPayload = Depends(get_sovereign_creator), s: PlannerService = Depends(service)):
    return response(await s.get(actor.sub, str(task_id)))


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def patch(
    task_id: uuid.UUID, body: TaskPatch, actor: TokenPayload = Depends(get_sovereign_creator), s: PlannerService = Depends(service)
):
    return response(await s.patch(actor.sub, str(task_id), body.model_dump(exclude_unset=True)))


@router.post("/tasks/{task_id}/dependencies", response_model=TaskResponse)
async def add_dependency(
    task_id: uuid.UUID, body: DependencyCreate, actor: TokenPayload = Depends(get_sovereign_creator), s: PlannerService = Depends(service)
):
    return response(await s.add_dependency(actor.sub, str(task_id), str(body.dependency_id)))


@router.delete("/tasks/{task_id}/dependencies/{dependency_id}", response_model=TaskResponse)
async def remove_dependency(
    task_id: uuid.UUID, dependency_id: uuid.UUID, actor: TokenPayload = Depends(get_sovereign_creator), s: PlannerService = Depends(service)
):
    return response(await s.remove_dependency(actor.sub, str(task_id), str(dependency_id)))


@router.get("/tasks/{task_id}/graph", response_model=GraphResponse)
async def graph(task_id: uuid.UUID, actor: TokenPayload = Depends(get_sovereign_creator), s: PlannerService = Depends(service)):
    task, predecessors, successors = await s.graph(actor.sub, str(task_id))
    return GraphResponse(
        task=response(task), predecessors=[response(x) for x in predecessors], successors=[response(x) for x in successors]
    )


@router.get("/tasks/{task_id}/topology", response_model=TopologyResponse)
async def topology(task_id: uuid.UUID, actor: TokenPayload = Depends(get_sovereign_creator), s: PlannerService = Depends(service)):
    task = await s.get(actor.sub, str(task_id))
    ordered = await s.topology(actor.sub, task.mission_id)
    return TopologyResponse(mission_id=task.mission_id, tasks=[response(x) for x in ordered])
