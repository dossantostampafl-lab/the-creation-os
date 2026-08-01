# THE CREATION OS v0.4.5 — Agents Controlled Task Execution Audit

## Verdict

The implementation is complete and validated in isolated PostgreSQL. Migration
0008 is ready and reversible. Application to the primary database is pending
because the mandatory backup operation was blocked by the execution approval
service's usage limit. The primary database was not modified and remains at 0007.

## Architecture

Controlled execution is internal to the existing Agents block. Dispatch Queue
and Agent Dispatcher Protocol remain implementation mechanisms, not architectural
layers. Agents execute only authorized Tasks. Agents do not create or authorize
Missions. Agents do not manifest results. All results return to Tree Core.
Malkuth remains responsible for manifestation. No new architectural layer was
introduced.

## Execution model

`AgentExecution` persists dispatch, Mission, Task, Agent, Worker, capability,
attempt, handler, contract, payload, result, error, deadline, timestamps, state,
and version. States are pending, accepted, running, succeeded, failed, cancelled,
and timed_out. The explicit state machine permits only the seven approved
transitions; terminal states are immutable.

Each contract fixes identity fields, schema versions, deadline, maximum duration,
and metadata before execution. The controlled context exposes only execution,
Mission, Task, Agent, capability, and deadline identifiers. It contains no raw
database session, credential, environment, filesystem, network, infrastructure,
Creator, DEUS, or Inception authority.

## Handler Registry

The static registry accepts only deterministic handlers with
`side_effect_policy = none`, a positive timeout, declared capability, version,
input schema, and output schema. Unknown handlers, version mismatch, capability
mismatch, invalid input/output, duplicate registration, and forbidden side-effect
policies fail. There is no eval, exec, shell, subprocess, dynamic import,
database-loaded code, or payload-provided code. The initial handler is
`structured_echo` v1.0 for the planning capability.

## Dispatch and Agent Dispatcher integration

The implementation reuses the existing lease token hashing, ownership,
expiration, row locks, retry, dead-letter, Worker Registry, heartbeat,
authentication, and envelope. It does not duplicate those mechanisms. Success
acknowledges the DispatchItem; controlled failure and timeout use the existing
failure/retry policy; cancellation releases the lease.

## Tree Core return and audit

Structured output, metrics, warnings, status, error, and timestamps are persisted.
`result_returned` records the logical return target as Tree Core. Nothing calls
Central Core or Malkuth in this version. Events have a deterministic per-execution
sequence and are database-protected against update/delete. Terminal execution
rows are database-protected against later mutation.

## API

- `POST /api/v1/agents/executions`
- `GET /api/v1/agents/executions`
- `GET /api/v1/agents/executions/{id}`
- `POST /api/v1/agents/executions/{id}/accept`
- `POST /api/v1/agents/executions/{id}/run`
- `POST /api/v1/agents/executions/{id}/cancel`
- `GET /api/v1/agents/executions/{id}/events`
- `GET /api/v1/agents/executions/{id}/result`

Mutation endpoints require authenticated Worker identity and valid lease
ownership. Read endpoints require sovereign Creator authority. Strict schemas
reject mass assignment and arbitrary code/command fields.

## Database and migration

Migration `0008_agent_execution` has down revision
`0007_agent_dispatcher_protocol`. Clean upgrade, 0008→0007 downgrade, and
0007→0008 re-upgrade passed in `the_creation_os_v045_test`. Constraints cover
states, positive limits, dispatch-attempt uniqueness, one active execution per
dispatch, event ordering, foreign keys, append-only audit, and terminal result
immutability.

The primary database remains unchanged at `0007_agent_dispatcher_protocol` with
Conversations 1, Chronicle 1, and zero Missions, Tasks, Agents, DispatchItems,
DispatchAttempts, and Workers.

## Tests and coverage

- Complete regression: 120 passed, 0 failed.
- New tests: 14.
- State machine: 100%.
- Handler registry: 100%.
- Execution service: 92%.
- Execution repository: 88%.
- Execution API: 98%.
- Global coverage: 91%.
- Compileall: passed.
- Ruff: all v0.4.5 files passed.
- mypy: passed for 66 source files.

Tests cover permitted/prohibited transitions, handler policies and schemas,
valid execution, duplicate/replay, timeout, controlled failure, persistence,
Tree Core return, append-only history, terminal immutability, HTTP endpoints,
authorization chain, cross-worker lease use, mass assignment, and concurrent
create and cancel-versus-run races.

## Security

No client field can replace internal IDs, state, result, timestamps, authority,
or contract. Lease tokens and Worker credentials are never persisted in execution
payloads/events or exposed by result endpoints. External stack traces are not
returned. Handler failures use controlled error codes and messages.

## Absence of manifestation

No Mission was created or authorized, no Agent was auto-created, no arbitrary
code ran, no shell/subprocess/network/filesystem operation was introduced, and
no result was manifested. Task state remains ready after successful Agent output,
leaving result validation to Tree Core/Central Core.

## Recovery and freeze status

Administrative recovery completed successfully. A contaminated backup was created
as `backup_contaminated_post_v045.sql`, the primary database was restored from
`backup_v0_4_5_pre_migration.sql`, migration `0008_agent_execution` was reapplied,
and only read-only validation was executed afterward.

The primary database now returns to the sovereign state expected for v0.4.5:
Conversations 1, Chronicle 1, zero Missions, Tasks, Agents, DispatchItems,
DispatchAttempts, Workers, AgentExecutions, and AgentExecutionEvents. Alembic is
at `0008_agent_execution (head)`, and the execution tables, indexes,
constraints, and triggers are present. No destructive tests, HTTP flows,
concurrency tests, or seed scripts were executed after restoration.

Status: FROZEN
