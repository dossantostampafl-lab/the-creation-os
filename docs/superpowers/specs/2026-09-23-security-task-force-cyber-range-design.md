# Security Task Force + Cyber Range — Design Specification (Phases 3–9)

Date: 2026-09-23  
Project: THE CREATION OS  
Branch: `feat/canonical-project-state`  
Status: **WRITTEN SPEC — CREATOR REVIEW REQUIRED BEFORE IMPLEMENTATION PLAN**

## 0. Purpose and non-negotiable outcome

The Creator must be able to state a mission in normal language. The system converts that intent into a bounded, auditable, risk-classified mission; assembles only the necessary specialist cells; executes only within explicitly granted capability; produces reproducible evidence; and returns a verified result without forcing the Creator to manually design the operational plan.

The Security Task Force is designed as an operational capability that can be developed and validated independently, then integrated with THE CREATION OS through explicit interfaces. The Cyber Range is its isolated training and verification environment. Neither component silently gains authority over production systems.

This specification consolidates Phases 3 through 9. Phases 1 and 2 are already closed: concept, architecture, and architectural stress test.

---

# Phase 3 — Mission Protocol

## 3.1 Mission entry

The Creator provides a natural-language objective. Example shape:

> Evaluate the security of system X within the authorized scope, preserve evidence, and report confirmed findings.

The Creator does **not** manually fill a low-level operational template.

## 3.2 Mission Compiler output

The Mission Compiler produces a `MissionContract` containing at minimum:

- `mission_id`
- `creator_id`
- `objective`
- `success_criteria`
- `authorized_targets`
- `excluded_targets`
- `allowed_action_classes`
- `risk_ceiling`
- `time_window`
- `resource_budget`
- `data_handling_class`
- `required_evidence`
- `rollback_requirements`
- `termination_conditions`
- `escalation_policy`
- `requested_specialties`
- `mission_version`

A compiled contract is immutable by default. Material changes create a new version. R5 changes become a new mission.

## 3.3 Mission states

Canonical states:

1. `DRAFT`
2. `COMPILED`
3. `AWAITING_AUTHORIZATION`
4. `AUTHORIZED`
5. `ASSEMBLING`
6. `ACTIVE`
7. `PAUSED`
8. `ESCALATED`
9. `VERIFYING`
10. `COMPLETED`
11. `ABORTED`

Terminal states: `COMPLETED`, `ABORTED`.

State transitions are durable and idempotent. A process restart must not create a second mission or duplicate an already-confirmed state-changing action.

## 3.4 Risk model

### R0 — informational
Read-only reasoning, retrieval, summarization and non-invasive analysis. Automatic.

### R1 — safe reversible action
Low-impact, scoped, reversible actions inside the mission boundary. Automatic if the mission authorizes the action class.

### R2 — delegated controlled action
Potentially meaningful action that is permitted only when explicitly delegated by the mission contract. The system may proceed without interrupting the Creator when delegation is present and policy passes.

### R3 — material state change
Actions with meaningful state change, impact, or operational consequence. Requires Creator approval.

### R4 — sensitive/high impact
Sensitive targets, broad reach, irreversible or high-consequence changes. Requires explicit Creator approval, stronger rollback controls and enhanced evidence requirements.

### R5 — new objective or scope expansion
Not an approval level inside the same mission. The system compiles a new mission.

## 3.5 Escalation rule

The system escalates when:

- proposed action exceeds mission risk ceiling;
- a discovered asset is outside executable scope;
- policy cannot decide safely;
- rollback is unavailable for an action that requires it;
- identity, target or authorization evidence is ambiguous;
- a requested action would cross from R2 into R3/R4;
- a material objective change triggers R5.

Silence is never approval.

## 3.6 Team assembly

Permanent core:

- Mission Commander
- Intel/Recon
- Evidence/Verification

Summonable cells:

- Red
- Blue
- Purple
- AppSec
- Cloud
- Identity
- Container
- Network
- Forensics
- additional domain specialists registered through capability governance

Team assembly is based on mission requirements and capability metadata, not on static always-on staffing.

## 3.7 Phase 3 acceptance criteria

Phase 3 is satisfied when the design supports:

- natural-language intent → deterministic structured contract;
- explicit scope and exclusions;
- R0–R5 classification;
- durable mission states;
- explicit escalation rules;
- dynamic team assembly;
- cancellation and kill switch semantics;
- versioned mission changes;
- no silent scope expansion.

---

# Phase 4 — Contracts and Components

## 4.1 Component boundaries

### DEUS
Receives Creator intent and preserves the semantic goal. DEUS does not directly authorize privileged execution.

### Mission Compiler
Transforms intent into a versioned `MissionContract`. It may ask for clarification only when required to avoid an unsafe or meaningless contract.

### SOPHIA — Chief Architect
Produces the execution architecture for the mission, resolves structural conflicts and identifies required specialist capabilities.

### Authorization Plane
Consumes mission contract, current action request, identity, target metadata, risk class and policy context. Returns an explicit permit/deny/escalate decision.

### OPA
Machine-evaluable policy engine used by Authorization Plane. Policy evaluation is deterministic and auditable.

### Mission Commander
Coordinates an authorized mission. It decomposes work, summons cells, tracks progress and pauses/escalates when authority is insufficient. It cannot self-grant capability.

### Temporal
Durable workflow state machine for mission orchestration, retries, timeouts, compensation and crash recovery.

### NATS/JetStream
Event transport between bounded services. Events are versioned and carry correlation ids.

### Target Graph
Represents authorized assets, discovered relationships, ownership, sensitivity, trust boundaries and scope state. Discovery does not imply execution permission.

### ATT&CK Knowledge Layer
Maps tactics, techniques, procedures, controls and scenarios to mission/cyber-range reasoning.

### Rust Gateway
Privileged execution boundary. It validates capability, target, action class, expiry, replay protection and policy decision before invoking an executor.

### Execution Sandbox
Kata Containers or Firecracker boundary for risky tooling. No executor receives broad host privileges by default.

### Verification
Evaluates evidence reproducibility, completeness and correlation before promoting a claim to a confirmed finding.

### Chronicle
Append-only mission decision/evidence journal with integrity metadata.

### The Creation Integration Adapter
Explicit interface between the independently validated Security Task Force and THE CREATION OS. No direct hidden coupling to internal tables is allowed.

## 4.2 Core contracts

### `ActionRequest`

- action id
- mission id/version
- task id
- actor identity
- target id
- requested capability
- risk class
- action parameters
- expected side effects
- rollback reference
- evidence expectation
- idempotency key

### `AuthorizationDecision`

- decision id
- action id
- decision: permit / deny / escalate
- policy version
- capability grant reference
- conditions
- expiry
- reason codes
- creator approval reference when required

### `CapabilityGrant`

- grant id
- mission id/version
- actor
- capability
- target selector
- action class
- issued at
- expires at
- max invocations / budget where applicable
- revocation state
- integrity/signature metadata

### `EvidenceRecord`

- evidence id
- mission/action/task correlation ids
- evidence type
- acquisition time
- source
- integrity hash
- storage reference
- sensitivity
- reproducibility metadata

### `Finding`

- finding id
- hypothesis
- status: hypothesis / probable / confirmed / not_reproduced / rejected
- attack evidence references
- defense evidence references
- affected assets
- severity methodology
- verification result
- remediation notes

## 4.3 Event namespace

Minimum versioned events:

- `mission.compiled.v1`
- `mission.authorization.requested.v1`
- `mission.authorized.v1`
- `mission.assembled.v1`
- `mission.started.v1`
- `mission.paused.v1`
- `mission.escalated.v1`
- `action.authorization.decided.v1`
- `action.started.v1`
- `action.completed.v1`
- `action.failed.v1`
- `evidence.recorded.v1`
- `finding.proposed.v1`
- `finding.verified.v1`
- `mission.completed.v1`
- `mission.aborted.v1`

Every event includes schema version, event id, timestamp, mission id, correlation id and causation id.

## 4.4 Phase 4 acceptance criteria

- every component has one primary responsibility;
- privileged execution can be traced to an authorization decision;
- contracts are versioned;
- components can be tested independently;
- no component bypasses Authorization Plane/Rust Gateway for privileged execution;
- the Integration Adapter is the only intended boundary to THE CREATION OS.

---

# Phase 5 — Security and Governance

## 5.1 Default-deny authority

Absence of a valid capability grant means deny. A stale mission, expired token, mismatched target or changed mission version invalidates the grant.

## 5.2 Identity

Every human, agent, service and executor has a stable identity. Service-to-service channels use authenticated transport. Identity is carried into Chronicle and evidence correlation.

## 5.3 Capability tokens

Capability tokens are short-lived and bound to:

- mission and version;
- task/action;
- actor;
- target selector;
- capability/action class;
- expiry;
- optional invocation/resource budget.

They are revocable. They are never reconstructed from memory after expiration.

## 5.4 Policy controls

OPA policy packages cover:

- risk ceilings;
- target scope;
- Creator approvals;
- action class;
- environment (Range vs real authorized environment);
- time window;
- data sensitivity;
- required rollback;
- required evidence;
- executor type;
- resource limits.

## 5.5 Isolation

- vulnerable Range targets bind to localhost/private isolated networks only;
- sandbox has no ambient access to host Docker socket;
- egress is denied or allowlisted by mission;
- secrets are injected per task and never persisted in evidence bodies;
- filesystem is disposable unless evidence output is explicitly exported;
- sandbox teardown occurs after mission/task completion.

## 5.6 Kill switches

Three independent stop paths:

1. Creator/global kill switch;
2. mission-level cancellation;
3. executor/sandbox local watchdog.

A kill switch revokes active grants and prevents new dispatch. Recovery requires an explicit new authorization transition.

## 5.7 Evidence integrity

Chronicle records hashes, timestamps, correlation ids and source metadata. Large evidence may reside in object/file storage, while Chronicle holds immutable references and integrity hashes.

## 5.8 Governance rules

- no self-escalation by an agent;
- no hidden privilege inheritance;
- no automatic promotion from Cyber Range to real environment;
- no confirmed finding without Verification;
- no production change based only on model confidence;
- policy version used for each decision must be retained.

## 5.9 Phase 5 acceptance criteria

- default-deny behavior demonstrated;
- revoked/expired grants fail closed;
- R3/R4 cannot execute without Creator approval evidence;
- R5 creates a new mission;
- cross-target replay is rejected;
- kill switches prevent new execution;
- sensitive data is redacted from routine logs.

---

# Phase 6 — Runtime and Integration with THE CREATION OS

## 6.1 Independent-first topology

The Security Task Force is implemented and validated as a bounded subsystem first. THE CREATION OS integration is through a documented adapter after subsystem acceptance gates pass.

## 6.2 Runtime services

Logical service set:

- `mission-compiler` — Python
- `sophia-planner` — Python
- `authorization-service` — Python + OPA
- `mission-commander` — Python + Temporal worker
- `event-bus` — NATS/JetStream
- `target-graph-service` — graph adapter/storage
- `verification-service` — Python
- `chronicle-service` — existing or adapted Chronicle boundary
- `execution-gateway` — Rust
- `sandbox-controller` — manages Kata/Firecracker execution
- `cyber-range-controller` — lifecycle/scenario interface
- `creation-integration-adapter` — explicit The Creation boundary

## 6.3 Durable data

PostgreSQL remains the authoritative durable store for mission metadata, authorization references, findings and audit indexes unless an existing repository component already owns the equivalent data. Existing THE CREATION OS tables are reused only after schema/ownership review; no duplicate truth source is introduced casually.

Temporal persists workflow state through its supported persistence layer. NATS/JetStream persists event streams according to retention policy. Redis may remain for existing hot-cache/rate-limiting functions but is not the source of mission truth.

## 6.4 Integration boundary

THE CREATION OS may provide:

- Creator identity;
- DEUS interaction;
- SOPHIA architectural context;
- validated memory retrieval;
- mission request initiation;
- Chronicle integration;
- final result presentation.

The Security Task Force returns:

- mission status;
- escalation requests;
- verified findings;
- evidence references;
- validated playbooks/knowledge eligible for memory;
- completion/abort report.

The Task Force does **not** inherit unrestricted access to internal THE CREATION OS services.

## 6.5 Failure handling

- Temporal retries only operations declared retry-safe;
- state-changing external actions require idempotency keys and/or compensation strategy;
- poison messages move to an observable dead-letter path;
- loss of OPA, identity, grant validation or Rust Gateway fails privileged execution closed;
- observability degradation does not silently convert failures into success;
- mission state can recover after process restart without duplicate execution.

## 6.6 Phase 6 acceptance criteria

- restart-safe mission orchestration;
- explicit adapter boundary to THE CREATION OS;
- no direct privilege coupling;
- NATS events correlated with Temporal workflow and Chronicle;
- durable mission state survives process/container restart;
- privileged boundary remains Rust Gateway → sandbox.

---

# Phase 7 — Testing and Validation

## 7.1 Test layers

### Unit
Mission compiler rules, risk classification, policy helpers, state machines, token validation, evidence classification.

### Contract
Schema compatibility for MissionContract, ActionRequest, AuthorizationDecision, CapabilityGrant, events and evidence records.

### Integration
Temporal + Postgres + NATS + OPA + Rust Gateway + sandbox controller.

### Cyber Range E2E
Authorized scenarios against intentionally vulnerable targets with attack/defense evidence and Verification.

### Property/invariant tests
Examples:

- expired grant can never authorize;
- target outside scope can never become executable without a new authorization;
- R3/R4 can never pass without approval reference;
- duplicate idempotency key cannot produce duplicate state change;
- mission completion cannot precede Verification when confirmed findings exist.

### Chaos/failure injection
Kill worker, restart NATS, restart Temporal worker, deny OPA, revoke token mid-task, terminate sandbox, simulate evidence storage failure.

### Security tests
Authn/authz, SSRF/egress boundaries, secret redaction, privilege isolation, path traversal, injection at action parameter boundaries, replay resistance.

## 7.2 Cyber Range validation pipeline

1. reset Range;
2. start isolated target scenario;
3. load mission contract;
4. verify target bindings are non-public;
5. execute authorized scenario;
6. collect Attack Evidence;
7. collect Defense Evidence where applicable;
8. run Verification;
9. record Chronicle entries;
10. teardown/reset;
11. replay enough of the scenario to prove reproducibility.

## 7.3 Certification evidence

Internal certification ladder:

- SH-1 Qualified
- SH-2 Advanced
- SH-3 Elite
- SH-X / Super Hacker Certified

Certification is based on defined scenario coverage, reproducibility, policy compliance, evidence quality and safe containment. It is not granted because an agent or model claims competence.

Exact SH-X scoring thresholds are a separate qualification specification and must be backed by implemented tests before operational certification is claimed.

## 7.4 Phase 7 release gates

No operational promotion unless:

- all unit/contract suites pass;
- critical integration suite passes;
- required E2E Range scenarios pass;
- no unresolved high-severity containment failure exists;
- kill switch test passes;
- restart/idempotency tests pass;
- evidence chain verifies;
- R3/R4 approval gate is demonstrated;
- scope expansion rejection is demonstrated.

---

# Phase 8 — Deployment and Operations

## 8.1 Local-first deployment

Primary deployment target for the current project is local Docker Desktop/LAN operation of THE CREATION OS, while dangerous/vulnerable Cyber Range workloads remain isolated and are not exposed to the LAN by default.

## 8.2 Compose/profile strategy

Recommended separation:

- existing core compose profile for THE CREATION OS;
- `security-task-force` profile for mission services;
- `cyber-range` profile for intentionally vulnerable targets and Range controller;
- optional observability profile.

The Range profile must not be required for ordinary Creator Interface startup.

## 8.3 Network zones

- `creation-core`: core services;
- `stf-control`: mission/auth/orchestration;
- `stf-execution`: gateway/sandbox control;
- `cyber-range`: isolated vulnerable targets;
- `observability`: telemetry plane.

No direct `cyber-range` → LAN ingress by default. Vulnerable applications bind to loopback or isolated container networks only.

## 8.4 Health and readiness

Every service exposes health/readiness appropriate to its dependency model. Readiness requires dependencies necessary for safe operation, not merely an open TCP port.

Privileged execution remains unavailable if policy, identity, grant validation or sandbox control is unhealthy.

## 8.5 Observability

Minimum telemetry:

- mission state transitions;
- authorization decisions by risk class;
- grant issuance/revocation/expiry;
- action latency and outcome;
- Temporal workflow failures/retries;
- NATS consumer lag;
- sandbox startup/teardown;
- evidence ingestion/verification;
- kill switch state;
- Range scenario results.

Use structured logs and OpenTelemetry-compatible traces/metrics where consistent with the existing platform.

## 8.6 Operational runbooks

Required runbooks:

- start/stop core;
- start/stop/reset Range;
- global kill switch;
- revoke mission grants;
- recover failed Temporal workflow;
- drain NATS consumers;
- verify Chronicle/evidence integrity;
- rotate credentials;
- restore from backup;
- diagnose authorization failure;
- diagnose sandbox failure.

## 8.7 Phase 8 acceptance criteria

- one-command/local documented startup for the intended profile;
- health checks reflect safe readiness;
- Range targets are not exposed to LAN by default;
- kill switch works during a live test mission;
- restart does not duplicate state-changing work;
- logs and traces correlate mission/action/evidence ids;
- backup/restore procedure exists for durable metadata.

---

# Phase 9 — Codex Handoff Package

## 9.1 Objective

After Creator review of this written specification, Codex receives a single canonical project context rather than reconstructing the architecture from chat.

## 9.2 Mandatory files for Codex

Codex must read:

1. `CONTEXT_BOOTSTRAP.md`
2. `PROJECT_STATE.yaml`
3. `FROZEN_DECISIONS.md`
4. `ARCHITECTURE_GRAPH.yaml`
5. `CHANGELOG_DECISIONS.md`
6. `ARCHITECTURE.md`
7. this specification
8. relevant current code/tests on the implementation branch

## 9.3 First implementation-session task: reconciliation audit

Before adding Security Task Force or Cyber Range code, Codex must verify:

- whether the previously reported Cyber Range v1 files exist on `main`, legacy branch, other branches, local-only work or Docker assets;
- the exact delta between current `main` and `fix/creator-interface-living-functional-scene`;
- which existing THE CREATION OS services already satisfy proposed contracts;
- whether current Chronicle, mission authorization, memory, worker and capability-governance code can be adapted rather than duplicated;
- whether current Docker topology conflicts with Temporal/NATS/OPA/sandbox additions.

The output of that audit updates `PROJECT_STATE.yaml` before new implementation begins.

## 9.4 Recommended implementation slices after audit

This is a sequencing boundary, **not yet the executable task-by-task implementation plan**:

1. contracts and state machines;
2. policy/risk engine and capability grants;
3. durable mission orchestration;
4. event bus and event schemas;
5. Rust privileged gateway;
6. isolated executor/sandbox controller;
7. Verification/evidence pipeline;
8. Cyber Range reconciliation and scenario runner;
9. THE CREATION OS integration adapter;
10. observability and runbooks;
11. E2E/chaos/security validation;
12. qualification/certification evidence.

Each slice requires tests before the next privilege layer is enabled.

## 9.5 Git/PR policy

- implement on dedicated feature branches/worktrees;
- no direct push to `main` for implementation;
- preserve legacy divergent branch until reconciliation closes;
- each PR states affected frozen decisions and evidence;
- schema/event breaking changes require version bump and migration path;
- no merge claim without test evidence.

## 9.6 Definition of ready for Codex implementation plan

The design is ready for detailed planning when the Creator reviews this document and either:

- approves it as written; or
- requests explicit revisions that are committed and re-reviewed.

Only after that gate should the Superpowers `writing-plans` workflow produce the task-by-task implementation plan.

---

# Cross-phase invariants

1. Creator remains the final escalation authority.
2. Mission intent is compiled; the Creator is not forced to hand-author low-level operational plans.
3. Command, authorization, execution and evidence remain separate.
4. Authority is ephemeral; knowledge may persist, privileges do not.
5. Scope does not expand silently.
6. Cyber Range is isolated and cannot authorize real-world action.
7. Findings require reproducible evidence.
8. R3/R4 require Creator approval; R5 is a new mission.
9. Runtime failure cannot be interpreted as authorization.
10. Implementation status is evidence-based.
11. Existing code is reconciled before new duplicate subsystems are created.
12. The repository, not conversational recollection, is the canonical project memory.

# Open verification item — not an architectural gap

The only material state uncertainty discovered during canonicalization is historical/repository reconciliation of the previously reported Cyber Range v1 and the heavily diverged legacy branch. This is intentionally represented as a verification item, not solved by inventing or recreating code.

# Review gate

**Creator action required before implementation planning:** review this specification. Approval authorizes creation of the detailed Codex implementation plan; it does not itself authorize privileged cyber operations outside explicitly authorized test systems and the Cyber Range.
