import uuid

from sqlalchemy.exc import IntegrityError

from app.core.domain import DomainError
from app.core.task_graph import TaskState, topological_order
from app.models.entities import Task, TaskDependency
from app.repositories.planner import PlannerRepository
from app.services.domain import NotFoundError


class PlannerError(DomainError):
    pass


class PlannerService:
    def __init__(self, repository: PlannerRepository):
        self.repository = repository

    async def _mission(self, mission_id, creator_id, authorized=False, lock=False):
        mission = await self.repository.mission(mission_id, lock=lock)
        if mission is None or mission.creator_id != creator_id:
            raise NotFoundError("Mission not found")
        if authorized and mission.status not in {"authorized", "distributed", "executing"}:
            raise PlannerError("Planner requires an authorized Mission")
        return mission

    def _new_task(self, **values):
        return Task(
            status="PENDING",
            input_json={},
            output_json={},
            error_json={},
            attempt_count=0,
            max_attempts=values["retry_limit"],
            idempotency_key=str(uuid.uuid4()),
            state=values.pop("state", TaskState.CREATED.value),
            **values,
        )

    async def create_task(self, creator_id, correlation_id=None, **values):
        await self._mission(values["mission_id"], creator_id, authorized=True, lock=True)
        if await self.repository.capability(values["required_capability_id"]) is None:
            raise NotFoundError("Capability not found")
        parent = values.get("parent_task_id")
        if parent:
            item = await self.repository.task(parent)
            if item is None or item.mission_id != values["mission_id"]:
                raise PlannerError("Invalid parent task")
        task = self._new_task(**values)
        cid = correlation_id or str(uuid.uuid4())
        try:
            await self.repository.add(task)
            await self.repository.add_event(
                event_type="task_created",
                aggregate_type="task",
                aggregate_id=task.id,
                actor_id=creator_id,
                actor_role="creator",
                correlation_id=cid,
                payload={"mission_id": task.mission_id, "state": task.state},
            )
            await self.repository.commit()
        except IntegrityError as exc:
            raise PlannerError("Duplicate or invalid Task") from exc
        return task

    async def patch(self, creator_id, task_id, changes, correlation_id=None):
        task = await self.repository.task(task_id, lock=True)
        if task is None:
            raise NotFoundError("Task not found")
        await self._mission(task.mission_id, creator_id, authorized=True)
        for key, value in changes.items():
            if value is not None:
                setattr(task, key, value)
        await self.repository.add_event(
            event_type="task_updated",
            aggregate_type="task",
            aggregate_id=task.id,
            actor_id=creator_id,
            actor_role="creator",
            correlation_id=correlation_id or str(uuid.uuid4()),
            payload={"fields": sorted(changes)},
        )
        await self.repository.commit()
        return task

    async def get(self, creator_id, task_id):
        task = await self.repository.task(task_id)
        if task is None:
            raise NotFoundError("Task not found")
        await self._mission(task.mission_id, creator_id)
        return task

    async def list(self, creator_id, mission_id):
        await self._mission(mission_id, creator_id)
        return await self.repository.tasks(mission_id)

    async def add_dependency(self, creator_id, task_id, dependency_id, correlation_id=None):
        task = await self.get(creator_id, task_id)
        await self._mission(task.mission_id, creator_id, authorized=True, lock=True)
        dependency = await self.get(creator_id, dependency_id)
        if task.mission_id != dependency.mission_id:
            raise PlannerError("Dependencies must share a Mission")
        cid = correlation_id or str(uuid.uuid4())
        try:
            await self.repository.add(TaskDependency(task_id=task_id, dependency_id=dependency_id))
            await self.topology(creator_id, task.mission_id)
            await self.repository.add_event(
                event_type="task_dependency_added",
                aggregate_type="task",
                aggregate_id=task.id,
                actor_id=creator_id,
                actor_role="creator",
                correlation_id=cid,
                payload={"dependency_id": dependency_id},
            )
            await self.repository.commit()
        except (ValueError, IntegrityError) as exc:
            await self.repository.rollback()
            if "cycle" in str(exc).lower():
                await self.repository.add_event(
                    event_type="cycle_creation_blocked",
                    aggregate_type="task",
                    aggregate_id=task_id,
                    actor_id=creator_id,
                    actor_role="creator",
                    correlation_id=cid,
                    payload={},
                )
                await self.repository.commit()
            raise PlannerError(str(exc)) from exc
        return task

    async def remove_dependency(self, creator_id, task_id, dependency_id, correlation_id=None):
        task = await self.get(creator_id, task_id)
        if await self.repository.delete_dependency(task_id, dependency_id) is None:
            raise NotFoundError("Dependency not found")
        await self.repository.add_event(
            event_type="task_dependency_removed",
            aggregate_type="task",
            aggregate_id=task.id,
            actor_id=creator_id,
            actor_role="creator",
            correlation_id=correlation_id or str(uuid.uuid4()),
            payload={"dependency_id": dependency_id},
        )
        await self.repository.commit()
        return task

    async def topology(self, creator_id, mission_id):
        tasks = await self.list(creator_id, mission_id)
        edges = await self.repository.dependencies(mission_id)
        order = topological_order({item.id for item in tasks}, {(item.task_id, item.dependency_id) for item in edges})
        mapping = {item.id: item for item in tasks}
        return [mapping[item_id] for item_id in order]

    async def graph(self, creator_id, task_id):
        task = await self.get(creator_id, task_id)
        tasks = await self.repository.tasks(task.mission_id)
        deps = await self.repository.dependencies(task.mission_id)
        mapping = {item.id: item for item in tasks}
        return (
            task,
            [mapping[x.dependency_id] for x in deps if x.task_id == task_id],
            [mapping[x.task_id] for x in deps if x.dependency_id == task_id],
        )

    async def plan(self, creator_id, mission_id, capability_id, correlation_id=None):
        mission = await self._mission(mission_id, creator_id, authorized=True, lock=True)
        if await self.repository.tasks(mission_id):
            raise PlannerError("Mission already planned")
        if await self.repository.capability(capability_id) is None:
            raise NotFoundError("Capability not found")
        cid = correlation_id or str(uuid.uuid4())
        names = ("Analyze objective", "Define strategy", "Validate plan", "Prepare capability handoff")
        result = []
        previous = None
        try:
            for index, name in enumerate(names):
                task = self._new_task(
                    mission_id=mission.id,
                    parent_task_id=previous,
                    name=name,
                    description=f"{name}: {mission.objective}",
                    required_capability_id=capability_id,
                    priority=100 - index,
                    retry_limit=3,
                    retry_count=0,
                    timeout_seconds=300,
                    estimated_duration=60,
                    state=TaskState.PLANNED.value,
                )
                await self.repository.add(task)
                if previous:
                    await self.repository.add(TaskDependency(task_id=task.id, dependency_id=previous))
                result.append(task)
                previous = task.id
            await self.repository.add_event(
                event_type="mission_plan_created",
                aggregate_type="mission",
                aggregate_id=mission.id,
                actor_id=creator_id,
                actor_role="creator",
                correlation_id=cid,
                payload={"task_count": len(result)},
            )
            await self.repository.commit()
        except IntegrityError as exc:
            raise PlannerError("Mission already planned") from exc
        return result
