from enum import StrEnum

from app.core.domain import InvalidStateTransition


class TaskState(StrEnum):
    CREATED = "created"
    PLANNED = "planned"
    WAITING = "waiting"
    READY = "ready"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TRANSITIONS = {
    TaskState.CREATED: {TaskState.PLANNED, TaskState.CANCELLED},
    TaskState.PLANNED: {TaskState.WAITING, TaskState.READY, TaskState.BLOCKED, TaskState.CANCELLED},
    TaskState.WAITING: {TaskState.READY, TaskState.BLOCKED, TaskState.CANCELLED},
    TaskState.BLOCKED: {TaskState.WAITING, TaskState.CANCELLED},
    TaskState.READY: {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.FAILED: {TaskState.WAITING, TaskState.CANCELLED},
    TaskState.COMPLETED: set(),
    TaskState.CANCELLED: set(),
}


def transition_task(current: str, target: TaskState) -> str:
    source = TaskState(current)
    if target not in TRANSITIONS[source]:
        raise InvalidStateTransition("task", source.value, target.value)
    return target.value


def topological_order(task_ids: set[str], edges: set[tuple[str, str]]) -> list[str]:
    predecessors: dict[str, set[str]] = {task_id: set() for task_id in task_ids}
    successors: dict[str, set[str]] = {task_id: set() for task_id in task_ids}
    for task_id, dependency_id in edges:
        if task_id not in task_ids or dependency_id not in task_ids or task_id == dependency_id:
            raise ValueError("Invalid task dependency")
        predecessors[task_id].add(dependency_id)
        successors[dependency_id].add(task_id)
    ready = sorted(task_id for task_id, deps in predecessors.items() if not deps)
    result = []
    while ready:
        current = ready.pop(0)
        result.append(current)
        for successor in sorted(successors[current]):
            predecessors[successor].discard(current)
            if not predecessors[successor] and successor not in result and successor not in ready:
                ready.append(successor)
                ready.sort()
    if len(result) != len(task_ids):
        raise ValueError("Task dependency cycle detected")
    return result
