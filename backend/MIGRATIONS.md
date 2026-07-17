# Migration compatibility note

`0001_initial` had not been applied to the persistent local Docker database when
the v0.3 stabilization began (`alembic current` returned no revision).

Two source defects were corrected before its first verified application:

- invalid Python syntax `psql.REAL[]()` was changed to `psql.ARRAY(psql.REAL())`;
- unused `CREATE/DROP EXTENSION vector` statements were removed because the
  schema stores embeddings as PostgreSQL `REAL[]`, not `vector`.

The resulting table type remains `REAL[]`. An external database that previously
ran a manually repaired copy of `0001` may retain an unused `vector` extension;
that does not change the application schema and must not be removed automatically.

## 0004_tree_core_foundation

Incrementally evolves the legacy `agents` table into the v0.4.1 Agent Registry.
It preserves legacy identifiers and foreign keys, adds registry lifecycle fields,
and introduces normalized `capabilities` and `agent_capabilities` tables.

Upgrade:

```bash
alembic upgrade 0004_tree_core_foundation
```

The migration does not modify Living Core, Creator, Chronicle, Conversation,
Inception, or Mission data.

## 0005_mission_planner

Extends the existing Task foundation with planner fields and normalized Task
dependencies. Previous migrations remain unchanged. No Dispatch tables are added.

## 0006_dispatch_queue

Creates `dispatch_items` and append-only `dispatch_attempts`, including controlled
states, leasing order index and a partial unique index for one active item per Task.

## 0007_agent_dispatcher_protocol

**FROZEN in v0.4.4.** The final audit validated upgrade, downgrade to 0006, and
re-upgrade to 0007 in an isolated PostgreSQL database.

Creates the persistent `workers` registry and normalized `worker_capabilities`
association. Worker UUIDs are unique, lifecycle states are constrained, and only
credential hashes are persisted. The migration does not modify the 0006 queue or
any Living Core table.

## 0008_agent_execution

Creates `agent_executions` and append-only `agent_execution_events`, controlled
states, attempt and active-dispatch uniqueness, foreign keys, history indexes,
and database triggers protecting event and terminal-result immutability. Upgrade
and downgrade were validated in isolated PostgreSQL. Application to the primary
database remains pending until its mandatory pre-migration backup can be created.

## 0009_tree_core_consolidation

Creates `mission_consolidations` for Tree Core result consolidation. The table is
unique per Mission and does not mutate Mission, Task, DispatchItem, or
AgentExecution state.

## 0010_central_core_decision

Creates immutable `mission_decisions` for Central Core. A Mission can have one
decision record. Central Core reads Tree Core consolidation data and records the
decision fingerprint and structured justification; it does not manifest.

## 0011_policy_reasoning

Adds policy reasoning records after Central Core decisions. Reasoning remains a
separate immutable step and does not alter the original decision.

## 0012_malkuth_manifestation

Adds persistence for Malkuth manifestation records. This is the manifestation
boundary and remains separate from Central Core and Tree Core.

## 0013_god_conversation

Adds GOD conversation orchestration records. GOD conversations do not create
Mission records automatically.

## 0014_sophia_understanding

Adds SOPHIA understanding records over GOD interactions. SOPHIA does not approve
or execute Missions.

## 0015_rockmam_assessment

Adds ROCKMAM possibility assessments. ROCKMAM assesses possibility without
manifesting results.

## 0016_memory_engine

Adds Creator memory persistence. Memory supports context retrieval without
changing ownership, authorization, or manifestation rules.

## 0017_automation_sdk

Adds automation connector foundations. Connectors remain capability-governed and
must not bypass Creator authorization.

## 0018_capability_persistence

Adds persistent registered capabilities for governance checks.

## 0019_opportunity_discovery

Adds opportunity and evidence persistence. Opportunities can be reviewed and, if
approved, converted to Inception; they do not create Mission automatically.

## 0020_continuous_perception

Adds perception sources, runs, and notifications. Perception collects and
notifies but does not approve opportunity or create Mission automatically.

## 0021_mission_authorization

Adds explicit Mission authorization scope. This is the expected release-candidate
Alembic head and the revision enforced by `/api/v1/health/ready`.
