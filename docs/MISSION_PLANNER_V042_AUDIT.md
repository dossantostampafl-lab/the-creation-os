# Mission Planner v0.4.2 Audit

## Files

The v0.4.2 implementation is located under `C:\Users\dossa\OneDrive\Área de Trabalho\THE CREATION OS` in:

- `backend/app/core/task_graph.py`
- `backend/app/repositories/planner.py`
- `backend/app/schemas/planner.py`
- `backend/app/services/planner.py`
- `backend/app/api/planner.py`
- `backend/alembic/versions/0005_mission_planner.py`
- `backend/tests/test_task_graph.py`
- `backend/tests/test_planner_integration.py`

## Nine endpoints and accepted schemas

- `POST /api/v1/tree-core/plan`: `mission_id`, `required_capability`.
- `GET /api/v1/tasks`: required `mission_id` query parameter.
- `POST /api/v1/tasks`: `mission_id`, optional `parent_task_id`, `name`, `description`,
  `required_capability`, `priority`, `retry_limit`, `timeout_seconds`, `estimated_duration`.
- `GET /api/v1/tasks/{id}`: UUID path.
- `PATCH /api/v1/tasks/{id}`: only `name`, `description`, and `priority`.
- `POST /api/v1/tasks/{id}/dependencies`: `dependency_id`.
- `DELETE /api/v1/tasks/{id}/dependencies/{dependency_id}`: UUID paths.
- `GET /api/v1/tasks/{id}/graph`: UUID path.
- `GET /api/v1/tasks/{id}/topology`: UUID path.

All request bodies reject extra fields. State, ownership, parent, retry counters,
timestamps, and execution fields cannot be mass-assigned.

## Invariants

Manual Task creation and planning require an `authorized` Mission owned by the
sovereign Creator. `parent_task_id` is optional but, when present, must reference
a Task in the same Mission. Dependencies are restricted to the same Mission and
the composite primary key `(task_id, dependency_id)` prevents duplicates.

The state machine permits only `created`, `planned`, `waiting`, `ready`, `blocked`,
`completed`, `failed`, and `cancelled`. No execution state exists and the public
PATCH does not change state.

## Atomicity and idempotency

The Planner locks the Mission, creates four deterministic Tasks and their linear
dependencies, records `mission_plan_created`, and commits once. A repeated or
concurrent plan request returns `409 Conflict`; it never silently duplicates Tasks.
The Mission itself is never changed.

The deterministic decomposition is: analyze objective, define strategy, validate
plan, and prepare capability handoff. Tasks use descending priorities 100..97 and
form a linear DAG.

## Graph algorithms

Cycle detection and topology use Kahn's algorithm. The ready set is sorted by UUID,
providing stable deterministic tie-breaking. Empty graphs, independent roots,
multiple leaves, chains, and diamonds are supported. Self, orphan, direct-cycle,
and indirect-cycle edges are rejected.

## Ownership and security

Every endpoint requires `get_sovereign_creator`. Mission ownership is checked
before Task access, so missing and cross-owner resources return 404. Invalid UUIDs
return 422; duplicate/cycle/domain conflicts return 409.

Critical actions record Chronicle events in the same transaction: `task_created`,
`task_updated`, `task_dependency_added`, `task_dependency_removed`, and
`mission_plan_created`. Rejected cycles record `cycle_creation_blocked` without
persisting the invalid edge.
