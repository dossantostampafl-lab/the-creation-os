from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable

from app.core.domain import DomainError
from app.core.task_graph import topological_order

VALID_TERMINAL_EXECUTION_STATES = frozenset({"succeeded", "failed", "cancelled", "timed_out"})
CONSOLIDATABLE_TASK_STATES = frozenset({"ready", "completed"})


@dataclass(frozen=True, order=True)
class ConsolidationIssue:
    code: str
    entity_type: str
    entity_id: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "detail": self.detail,
        }


class ConsolidationError(DomainError):
    def __init__(self, issues: Iterable[ConsolidationIssue]) -> None:
        self.issues = tuple(sorted(set(issues)))
        summary = "; ".join(f"{item.code}:{item.entity_id}" for item in self.issues)
        super().__init__(f"Mission consolidation rejected: {summary}")


@dataclass(frozen=True)
class ConsolidationDocument:
    status: str
    payload: dict[str, Any]
    inconsistencies: list[dict[str, str]]
    completeness: dict[str, Any]
    fingerprint: str


def _canonical(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def _issue(code: str, entity_type: str, entity_id: str, detail: str) -> ConsolidationIssue:
    return ConsolidationIssue(code, entity_type, str(entity_id), detail)


def build_consolidation(
    mission: Any,
    tasks: Iterable[Any],
    dependencies: Iterable[Any],
    dispatch_items: Iterable[Any],
    executions: Iterable[Any],
) -> ConsolidationDocument:
    task_list = list(tasks)
    dependency_list = list(dependencies)
    dispatch_list = list(dispatch_items)
    execution_list = list(executions)
    issues: list[ConsolidationIssue] = []

    if mission.status != "authorized":
        issues.append(_issue("mission_not_authorized", "mission", mission.id, "Mission must remain authorized"))

    task_map: dict[str, Any] = {}
    for task in task_list:
        if task.id in task_map:
            issues.append(_issue("duplicate_task", "task", task.id, "Task appears more than once"))
        task_map[task.id] = task
        if task.mission_id != mission.id:
            issues.append(_issue("task_mission_mismatch", "task", task.id, "Task belongs to another Mission"))
        if task.state not in CONSOLIDATABLE_TASK_STATES:
            issues.append(_issue("task_not_ready", "task", task.id, "Task is not technically ready for consolidation"))
    if not task_map:
        issues.append(_issue("mission_without_tasks", "mission", mission.id, "Mission has no Tasks"))

    edges: set[tuple[str, str]] = set()
    for dependency in dependency_list:
        edge = (dependency.task_id, dependency.dependency_id)
        if edge in edges:
            issues.append(
                _issue("duplicate_dependency", "task_dependency", f"{edge[0]}:{edge[1]}", "Dependency appears more than once")
            )
        edges.add(edge)
        if dependency.task_id not in task_map or dependency.dependency_id not in task_map:
            issues.append(
                _issue("orphan_dependency", "task_dependency", f"{edge[0]}:{edge[1]}", "Dependency crosses the Mission boundary")
            )

    if task_map and not any(item.code == "orphan_dependency" for item in issues):
        try:
            task_order = topological_order(set(task_map), edges)
        except ValueError as exc:
            issues.append(_issue("invalid_task_graph", "mission", mission.id, str(exc)))
            task_order = sorted(task_map)
    else:
        task_order = sorted(task_map)

    dispatch_map: dict[str, Any] = {}
    dispatches_by_task: dict[str, list[Any]] = {task_id: [] for task_id in task_map}
    for item in dispatch_list:
        if item.id in dispatch_map:
            issues.append(_issue("duplicate_dispatch", "dispatch_item", item.id, "Dispatch Item appears more than once"))
        dispatch_map[item.id] = item
        task = task_map.get(item.task_id)
        if task is None:
            issues.append(_issue("dispatch_orphan_task", "dispatch_item", item.id, "Dispatch Item references an unknown Task"))
            continue
        dispatches_by_task[item.task_id].append(item)
        if item.mission_id != mission.id:
            issues.append(_issue("dispatch_mission_mismatch", "dispatch_item", item.id, "Dispatch Item belongs to another Mission"))
        if item.capability_id != task.required_capability_id:
            issues.append(_issue("dispatch_capability_mismatch", "dispatch_item", item.id, "Dispatch capability differs from Task"))
        if task.agent_id is not None and item.agent_id != task.agent_id:
            issues.append(_issue("dispatch_agent_mismatch", "dispatch_item", item.id, "Dispatch Agent differs from Task"))
        if item.state != "acknowledged":
            issues.append(_issue("dispatch_not_acknowledged", "dispatch_item", item.id, "Dispatch Item is not acknowledged"))

    for task_id, items in dispatches_by_task.items():
        if not items:
            issues.append(_issue("missing_dispatch", "task", task_id, "Task has no Dispatch Item"))
        elif len(items) > 1:
            issues.append(_issue("duplicate_task_dispatch", "task", task_id, "Task has multiple Dispatch Items"))

    successful_by_task: dict[str, list[Any]] = {task_id: [] for task_id in task_map}
    seen_execution_ids: set[str] = set()
    for execution in execution_list:
        if execution.id in seen_execution_ids:
            issues.append(_issue("duplicate_execution", "agent_execution", execution.id, "Execution appears more than once"))
        seen_execution_ids.add(execution.id)
        dispatch = dispatch_map.get(execution.dispatch_item_id)
        task = task_map.get(execution.task_id)
        if dispatch is None:
            issues.append(
                _issue("execution_orphan_dispatch", "agent_execution", execution.id, "Execution references an unknown Dispatch Item")
            )
        if task is None:
            issues.append(_issue("execution_orphan_task", "agent_execution", execution.id, "Execution references an unknown Task"))
        if execution.mission_id != mission.id:
            issues.append(_issue("execution_mission_mismatch", "agent_execution", execution.id, "Execution belongs to another Mission"))
        if dispatch is not None:
            if execution.task_id != dispatch.task_id:
                issues.append(_issue("execution_task_mismatch", "agent_execution", execution.id, "Execution Task differs from Dispatch"))
            if execution.agent_id != dispatch.agent_id:
                issues.append(_issue("execution_agent_mismatch", "agent_execution", execution.id, "Execution Agent differs from Dispatch"))
            if execution.capability_id != dispatch.capability_id:
                issues.append(
                    _issue("execution_capability_mismatch", "agent_execution", execution.id, "Execution capability differs from Dispatch")
                )
        if execution.state not in VALID_TERMINAL_EXECUTION_STATES:
            issues.append(_issue("execution_not_terminal", "agent_execution", execution.id, "Execution is not terminal"))
        elif execution.state == "succeeded":
            if execution.output_payload is None:
                issues.append(_issue("execution_without_result", "agent_execution", execution.id, "Successful execution has no result"))
            elif task is not None:
                successful_by_task[task.id].append(execution)

    for task_id, successful in successful_by_task.items():
        if not successful:
            issues.append(_issue("missing_successful_execution", "task", task_id, "Task has no successful result"))
        elif len(successful) > 1:
            issues.append(_issue("duplicate_task_result", "task", task_id, "Task has multiple successful results"))

    if issues:
        raise ConsolidationError(issues)

    task_payloads: list[dict[str, Any]] = []
    for task_id in task_order:
        task = task_map[task_id]
        dispatch = dispatches_by_task[task_id][0]
        execution = successful_by_task[task_id][0]
        task_payloads.append(
            {
                "task_id": task.id,
                "name": task.name,
                "dependencies": sorted(dependency_id for current_id, dependency_id in edges if current_id == task.id),
                "dispatch_item_id": dispatch.id,
                "agent_execution_id": execution.id,
                "agent_id": execution.agent_id,
                "capability_id": execution.capability_id,
                "result": {
                    "output": execution.output_payload,
                    "metrics": execution.result_metrics or {},
                    "warnings": execution.result_warnings or [],
                },
            }
        )

    payload = _canonical(
        {
            "schema_version": "1.0",
            "mission_id": mission.id,
            "task_count": len(task_payloads),
            "tasks": task_payloads,
        }
    )
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    completeness = {
        "complete": True,
        "expected_tasks": len(task_payloads),
        "consolidated_tasks": len(task_payloads),
        "pending_tasks": 0,
    }
    return ConsolidationDocument(
        status="complete",
        payload=payload,
        inconsistencies=[],
        completeness=completeness,
        fingerprint=hashlib.sha256(serialized).hexdigest(),
    )
