# Security Task Force + Cyber Range Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the reviewed Security Task Force + Cyber Range design as a bounded, auditable subsystem of THE CREATION OS, with mission-scoped authority, durable orchestration, isolated execution, evidence verification, local-first deployment, and no silent privilege or scope expansion.

**Architecture:** Extend the existing Mission/Capability/Chronicle model instead of creating a second source of truth. Python owns mission contracts, compilation, authorization coordination, orchestration, verification and THE CREATION OS integration; Temporal provides durable workflows; NATS/JetStream transports versioned events; OPA evaluates policy; a Rust gateway is the privileged edge; Kata Containers or Firecracker provide the only privileged sandbox backend selected after host-capability evidence. Cyber Range remains an isolated validation environment and never grants production authority.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy asyncio, PostgreSQL/pgvector, Redis where already used, Temporal, NATS/JetStream, OPA/Rego, Rust + Axum/Tokio/Serde, Docker Compose, pytest, cargo test, OpenTelemetry-compatible telemetry.

**Spec:** `docs/superpowers/specs/2026-09-23-security-task-force-cyber-range-design.md`

**Binding amendment:** `docs/superpowers/specs/2026-09-23-security-task-force-cyber-range-amendment-01.md`

## Global Constraints

- Read `CONTEXT_BOOTSTRAP.md`, `PROJECT_STATE.yaml`, `FROZEN_DECISIONS.md`, `ARCHITECTURE_GRAPH.yaml`, and `CHANGELOG_DECISIONS.md` before implementation.
- Work in a dedicated branch/worktree; do not implement directly on `main`.
- Preserve `fix/creator-interface-living-functional-scene` until reconciliation is complete.
- Reconcile existing Cyber Range evidence before recreating Range assets.
- Creator remains final escalation authority; silence is never approval.
- R0/R1 may execute automatically only inside approved scope; R2 requires delegated authority; R3/R4 require Creator approval; R5 creates a new mission.
- Authorization must bind mission id/version, actor, target, execution environment, capability/action class, expiry and action/idempotency identity.
- `CYBER_RANGE` authority can never be reused as `REAL_AUTHORIZED` authority.
- No component may combine command, authorization, privileged execution and evidence authority.
- Privileged execution is `Authorization Plane -> Rust Gateway -> Kata/Firecracker sandbox`; no raw host shell and no ambient Docker socket.
- If neither Kata nor Firecracker satisfies the host probe, privileged execution remains unavailable and fails closed.
- Findings are not `confirmed` until Verification validates linked evidence.
- Existing Chronicle remains the canonical append-only audit/evidence chain unless reconciliation proves it cannot satisfy the contract.
- Status labels are evidence-based: `DESIGN_APPROVED`, `IMPLEMENTED`, `TESTED`, `VERIFIED_OPERATIONAL` are distinct.

## Review Focus

1. **Environment replay:** a grant valid for `CYBER_RANGE` must fail for `REAL_AUTHORIZED` even with the same target and capability; Task 5 owns the regression test.
2. **Stale authority:** expired, revoked or previous-mission-version grants must fail closed; Task 5 owns these tests.
3. **Crash/idempotency:** worker, Temporal or NATS restarts must not duplicate a state-changing action; Tasks 6, 7 and 14 own these tests.
4. **Isolation unavailability:** unsupported host virtualization must not downgrade to Docker/host execution; Task 9 owns the fail-closed test.
5. **Evidence promotion:** a model/agent assertion without reproducible evidence must never become a confirmed finding; Task 10 owns this invariant test.

---

### Task 1: Reconciliation audit and implementation worktree

**Files:**
- Create: `docs/superpowers/audits/2026-09-23-security-task-force-reconciliation.md`
- Modify: `PROJECT_STATE.yaml`
- Modify: `CHANGELOG_DECISIONS.md`

**Interfaces:**
- Consumes: canonical branch state and repository history.
- Produces: verified inventory of reusable Mission, Capability, Chronicle, worker, Docker and Cyber Range assets; exact implementation baseline SHA.

- [ ] **Step 1: Create an isolated implementation worktree**

```bash
git fetch origin
git worktree add ../the-creation-os-stf -b feat/security-task-force-runtime feat/canonical-project-state
cd ../the-creation-os-stf
git status --short --branch
```

Expected: branch `feat/security-task-force-runtime`, clean worktree.

- [ ] **Step 2: Record branch and Range evidence**

```bash
git rev-list --left-right --count main...fix/creator-interface-living-functional-scene
git log --all --oneline --decorate --grep='Cyber Range\|cyber-range\|WebGoat\|Juice Shop\|CALDERA'
git ls-tree -r --name-only main | grep -Ei 'cyber.?range|webgoat|webwolf|juice|caldera|range.controller|qualification' || true
git ls-tree -r --name-only fix/creator-interface-living-functional-scene | grep -Ei 'cyber.?range|webgoat|webwolf|juice|caldera|range.controller|qualification' || true
```

Copy the exact commit ids and file paths into the audit document; do not infer implementation from chat history.

- [ ] **Step 3: Inventory reusable current code**

```bash
git grep -nE 'class Mission|MissionAuthorization|CapabilityGateway|class Chronicle|idempotency_key|kill switch|kill_switch' -- backend/app backend/tests
```

The audit must explicitly classify each candidate as `REUSE`, `ADAPT`, `REPLACE`, or `ABSENT`, with repository path and reason.

- [ ] **Step 4: Update canonical state from evidence**

Update `PROJECT_STATE.yaml` with `implementation_baseline_sha`, reconciliation evidence, and `cyber_range.repository_verification_on_main` as either `VERIFIED_PRESENT`, `VERIFIED_ABSENT`, or `PARTIAL`. Append a decision-log entry containing the commands and result; do not change any frozen architectural decision.

- [ ] **Step 5: Verify and commit**

```bash
git diff --check
git status --short
git add docs/superpowers/audits/2026-09-23-security-task-force-reconciliation.md PROJECT_STATE.yaml CHANGELOG_DECISIONS.md
git commit -m "docs: reconcile security task force implementation baseline"
```

---

### Task 2: Canonical mission contracts and state machine

**Files:**
- Create: `backend/app/security_task_force/__init__.py`
- Create: `backend/app/security_task_force/contracts.py`
- Create: `backend/app/security_task_force/state_machine.py`
- Test: `backend/tests/test_stf_contracts.py`
- Test: `backend/tests/test_stf_state_machine.py`

**Interfaces:**
- Consumes: Creator intent metadata and existing mission identity.
- Produces: `MissionContract`, `ActionRequest`, `AuthorizationDecision`, `CapabilityGrant`, `EvidenceRecord`, `Finding`, `RiskClass`, `ExecutionEnvironment`, `MissionState`, `transition_mission_state()`.

- [ ] **Step 1: Write failing contract tests**

```python
from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError

from app.security_task_force.contracts import ExecutionEnvironment, MissionContract, RiskClass


def valid_contract() -> MissionContract:
    now = datetime.now(timezone.utc)
    return MissionContract(
        mission_id="11111111-1111-1111-1111-111111111111",
        creator_id="22222222-2222-2222-2222-222222222222",
        objective="Validate an authorized test service",
        success_criteria=["verified result"],
        authorized_targets=["svc:test"],
        excluded_targets=[],
        authorized_environments=[ExecutionEnvironment.CYBER_RANGE],
        allowed_action_classes=["read", "validate"],
        risk_ceiling=RiskClass.R2,
        time_window_start=now,
        time_window_end=now + timedelta(hours=1),
        resource_budget={"max_actions": 10},
        data_handling_class="internal",
        required_evidence=["action_log"],
        rollback_requirements=[],
        termination_conditions=["success", "timeout", "kill_switch"],
        escalation_policy="creator_for_r3_r4",
        requested_specialties=["blue"],
        mission_version=1,
    )


def test_environment_is_mandatory():
    payload = valid_contract().model_dump()
    payload["authorized_environments"] = []
    with pytest.raises(ValidationError):
        MissionContract.model_validate(payload)
```

- [ ] **Step 2: Run tests and verify failure**

```bash
cd backend
pytest tests/test_stf_contracts.py -q
```

Expected: import/module failure because the STF contracts do not exist yet.

- [ ] **Step 3: Implement canonical enums and models**

```python
class RiskClass(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"
    R5 = "R5"

class ExecutionEnvironment(StrEnum):
    CYBER_RANGE = "CYBER_RANGE"
    REAL_AUTHORIZED = "REAL_AUTHORIZED"

class MissionState(StrEnum):
    DRAFT = "DRAFT"
    COMPILED = "COMPILED"
    AWAITING_AUTHORIZATION = "AWAITING_AUTHORIZATION"
    AUTHORIZED = "AUTHORIZED"
    ASSEMBLING = "ASSEMBLING"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ESCALATED = "ESCALATED"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
```

`MissionContract` must model every field in Phase 3 plus mandatory `authorized_environments`. `CapabilityGrant` must include mission id/version, actor, target selector, environment selector, capability, action class, issued/expires timestamps, invocation budget, revocation state and integrity metadata.

- [ ] **Step 4: Implement and test allowed transitions**

`transition_mission_state(current, requested)` must reject transitions not present in an explicit transition map and must treat `COMPLETED` and `ABORTED` as terminal.

```bash
pytest tests/test_stf_contracts.py tests/test_stf_state_machine.py -q
ruff check app/security_task_force tests/test_stf_contracts.py tests/test_stf_state_machine.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/security_task_force backend/tests/test_stf_contracts.py backend/tests/test_stf_state_machine.py
git commit -m "feat: add security task force mission contracts"
```

---

### Task 3: Mission Compiler validation boundary

**Files:**
- Create: `backend/app/security_task_force/compiler.py`
- Test: `backend/tests/test_stf_mission_compiler.py`

**Interfaces:**
- Consumes: `MissionReasoner.compile(intent, context) -> dict[str, Any]`.
- Produces: `compile_mission(intent, creator_id, context, reasoner) -> CompiledMission`, containing normalized `MissionContract`, compiler version, input hash and validation evidence.

- [ ] **Step 1: Write failing tests for non-deterministic reasoner output**

Create a fake reasoner that returns fields in different order on successive calls. Assert that validation is based on normalized contract content and policy checks, not raw model text. Add tests that missing environment, invalid risk ceiling and invalid time window are rejected before authorization.

- [ ] **Step 2: Run failing tests**

```bash
cd backend
pytest tests/test_stf_mission_compiler.py -q
```

- [ ] **Step 3: Implement reasoner protocol and normalized verification**

```python
class MissionReasoner(Protocol):
    async def compile(self, *, intent: str, context: dict[str, Any]) -> dict[str, Any]: ...

@dataclass(frozen=True)
class CompiledMission:
    contract: MissionContract
    compiler_version: str
    normalized_sha256: str
    input_sha256: str
    validation_rules: tuple[str, ...]
```

Normalize with `MissionContract.model_dump(mode="json")`, canonical JSON (`sort_keys=True`, compact separators), and SHA-256. Validation must run after model parsing and before returning `CompiledMission`.

- [ ] **Step 4: Verify tests**

```bash
pytest tests/test_stf_mission_compiler.py -q
```

Expected: schema-invalid and policy-invalid candidates fail; normalized verification remains stable for semantically identical contracts.

- [ ] **Step 5: Commit**

```bash
git add backend/app/security_task_force/compiler.py backend/tests/test_stf_mission_compiler.py
git commit -m "feat: add verifiable mission compiler boundary"
```

---

### Task 4: Persist versioned contracts, grants, decisions and evidence indexes

**Files:**
- Create: `backend/app/models/security_task_force.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0010_security_task_force_core.py`
- Create: `backend/app/security_task_force/repository.py`
- Test: `backend/tests/test_stf_repository.py`
- Test: `backend/tests/test_stf_postgres_integration.py`

**Interfaces:**
- Consumes: canonical STF contracts.
- Produces: durable mission-contract versions, authorization decisions, grants, replay nonces, evidence indexes and findings linked to the existing `missions` and `chronicles` tables.

- [ ] **Step 1: Write repository tests before schema changes**

Tests must prove: contract version uniqueness by `(mission_id, mission_version)`, idempotent decision insert by `decision_id`, unique replay nonce, grant revocation persistence, and finding-to-evidence references.

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend
pytest tests/test_stf_repository.py tests/test_stf_postgres_integration.py -q
```

- [ ] **Step 3: Add tables without duplicating existing Mission/Chronicle truth**

Create these tables: `stf_mission_contracts`, `stf_authorization_decisions`, `stf_capability_grants`, `stf_execution_nonces`, `stf_evidence_index`, `stf_findings`. Every row must carry `mission_id`; contract/decision/grant records also carry `mission_version`. Evidence bodies stay outside the index when large; the index stores storage reference, SHA-256, sensitivity and correlation ids.

- [ ] **Step 4: Verify migration and repository behavior**

```bash
alembic upgrade head
pytest tests/test_stf_repository.py tests/test_stf_postgres_integration.py -q
```

Expected: migration succeeds on a clean PostgreSQL database and tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models backend/app/security_task_force/repository.py backend/alembic/versions/0010_security_task_force_core.py backend/tests/test_stf_repository.py backend/tests/test_stf_postgres_integration.py
git commit -m "feat: persist security task force authority and evidence state"
```

---

### Task 5: Authorization Plane, R0-R5 policy and ephemeral capability grants

**Files:**
- Create: `backend/app/security_task_force/authorization.py`
- Create: `backend/app/security_task_force/grants.py`
- Create: `backend/app/security_task_force/opa_client.py`
- Create: `policy/stf/authorization.rego`
- Modify: `backend/app/capabilities/mission_authorization.py`
- Modify: `backend/app/capabilities/gateway.py`
- Test: `backend/tests/test_stf_authorization.py`
- Test: `backend/tests/test_stf_grants.py`

**Interfaces:**
- Consumes: `MissionContract`, `ActionRequest`, Creator approval reference, actor identity and OPA result.
- Produces: explicit `AuthorizationDecision` and short-lived `CapabilityGrant`.

- [ ] **Step 1: Write invariant tests**

Tests must cover: default deny; target mismatch; environment mismatch; Range grant used in real environment; expired grant; revoked grant; stale mission version; R3/R4 without Creator approval; R5 returning `escalate_new_mission`; deny-wins capability list behavior.

- [ ] **Step 2: Run failing authorization tests**

```bash
cd backend
pytest tests/test_stf_authorization.py tests/test_stf_grants.py -q
```

- [ ] **Step 3: Implement policy input and OPA package**

Policy input must include:

```json
{
  "mission_id": "...",
  "mission_version": 1,
  "actor": "...",
  "target": "svc:test",
  "environment": "CYBER_RANGE",
  "capability": "validate",
  "action_class": "read",
  "risk_class": "R2",
  "risk_ceiling": "R2",
  "creator_approval_ref": null,
  "rollback_available": true,
  "time_window_valid": true
}
```

OPA result is only `permit`, `deny`, or `escalate`, plus stable reason codes. Loss of OPA is `deny` for privileged execution.

- [ ] **Step 4: Issue signed grants only after permit**

Grant signing payload must cover mission id/version, actor, target selector, environment selector, capability, action class, expiry and budget. Use an HMAC key injected from environment for the first implementation; do not persist the raw signing key in Chronicle or evidence.

```bash
pytest tests/test_stf_authorization.py tests/test_stf_grants.py tests/test_capability_gateway.py -q
```

Expected: all invariant tests pass and existing capability gateway tests remain green.

- [ ] **Step 5: Commit**

```bash
git add backend/app/security_task_force backend/app/capabilities policy/stf backend/tests/test_stf_authorization.py backend/tests/test_stf_grants.py
git commit -m "feat: enforce mission scoped authorization and grants"
```

---

### Task 6: Versioned event envelope, transactional outbox and NATS/JetStream adapter

**Files:**
- Create: `backend/app/security_task_force/events.py`
- Create: `backend/app/security_task_force/outbox.py`
- Create: `backend/app/security_task_force/event_bus.py`
- Create: `backend/alembic/versions/0011_stf_outbox.py`
- Modify: `backend/pyproject.toml`
- Test: `backend/tests/test_stf_events.py`
- Test: `backend/tests/test_stf_outbox.py`

**Interfaces:**
- Consumes: state changes committed in PostgreSQL.
- Produces: durable versioned events with `event_id`, `schema_version`, `timestamp`, `mission_id`, `correlation_id`, `causation_id` and typed payload.

- [ ] **Step 1: Write event and outbox tests**

Assert the exact namespace from the spec, unique `event_id`, retry-safe publish, and that an acknowledged outbox row is never published twice by the same dispatcher cycle.

- [ ] **Step 2: Add NATS dependency and fail tests first**

Add `nats-py` to `backend/pyproject.toml`, install the project, then run:

```bash
cd backend
pip install -e '.[dev]'
pytest tests/test_stf_events.py tests/test_stf_outbox.py -q
```

- [ ] **Step 3: Implement transactional outbox**

`OutboxRecord` fields: id, event id, subject, payload JSON, created at, published at, attempt count, last error. Business state and outbox insert must commit in the same database transaction. Publisher uses JetStream message id equal to event id.

- [ ] **Step 4: Verify retry behavior**

```bash
pytest tests/test_stf_events.py tests/test_stf_outbox.py -q
```

Expected: simulated broker failure leaves row unpublished; retry publishes exactly once logically using stable event id.

- [ ] **Step 5: Commit**

```bash
git add backend/app/security_task_force backend/alembic/versions/0011_stf_outbox.py backend/pyproject.toml backend/tests/test_stf_events.py backend/tests/test_stf_outbox.py
git commit -m "feat: add durable security task force event outbox"
```

---

### Task 7: Temporal durable mission orchestration and kill-switch semantics

**Files:**
- Create: `backend/app/security_task_force/workflows.py`
- Create: `backend/app/security_task_force/activities.py`
- Create: `backend/app/security_task_force/temporal_worker.py`
- Create: `backend/app/security_task_force/kill_switch.py`
- Modify: `backend/pyproject.toml`
- Test: `backend/tests/test_stf_workflow.py`
- Test: `backend/tests/test_stf_kill_switch.py`

**Interfaces:**
- Consumes: authorized `MissionContract`, task plan and authorization service.
- Produces: durable state transitions, retries only for retry-safe activities, cancellation, escalation and mission completion/abort signals.

- [ ] **Step 1: Write workflow tests**

Use Temporal's test environment. Prove restart/replay does not re-run an already-recorded state-changing action, mission cancellation reaches `ABORTED`, kill switch prevents new dispatch, and a confirmed finding forces `VERIFYING` before `COMPLETED`.

- [ ] **Step 2: Add Temporal SDK and run failing tests**

Add `temporalio` to `backend/pyproject.toml`, then:

```bash
cd backend
pip install -e '.[dev]'
pytest tests/test_stf_workflow.py tests/test_stf_kill_switch.py -q
```

- [ ] **Step 3: Implement workflow**

`MissionWorkflow.run()` follows: authorize -> assemble -> active -> verify -> complete/abort. Privileged activities receive only an `action_id`; they reload current authorization/grant state instead of trusting stale workflow payloads.

- [ ] **Step 4: Verify cancellation and replay**

```bash
pytest tests/test_stf_workflow.py tests/test_stf_kill_switch.py tests/test_cancellation_invariant.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/security_task_force backend/pyproject.toml backend/tests/test_stf_workflow.py backend/tests/test_stf_kill_switch.py
git commit -m "feat: orchestrate security missions with Temporal"
```

---

### Task 8: Rust privileged execution gateway

**Files:**
- Create: `security_gateway/Cargo.toml`
- Create: `security_gateway/src/main.rs`
- Create: `security_gateway/src/contracts.rs`
- Create: `security_gateway/src/auth.rs`
- Create: `security_gateway/src/replay.rs`
- Create: `security_gateway/src/sandbox/mod.rs`
- Test: `security_gateway/tests/gateway_contract.rs`

**Interfaces:**
- Consumes: signed `ExecutionEnvelope` plus live grant/authorization validation result.
- Produces: execution dispatch only to a registered sandbox tool adapter; never arbitrary host shell.

- [ ] **Step 1: Write Rust contract tests**

`ExecutionEnvelope` fields must include mission id/version, action id, actor, target, environment, capability, action class, risk class, decision id, grant id, expiry, nonce, parameters hash and signature. Tests reject expired envelope, wrong environment, tampered parameters hash, reused nonce and missing decision id.

- [ ] **Step 2: Create crate and verify tests fail**

```bash
cargo new security_gateway --bin
cd security_gateway
cargo add axum tokio --features tokio/full
cargo add serde --features derive
cargo add serde_json uuid time hmac sha2 subtle
cargo test
```

Replace the generated source with the planned modules; initial contract tests must fail before implementation.

- [ ] **Step 3: Implement validation pipeline**

Validation order is fixed: parse -> schema -> expiry -> signature -> nonce replay -> mission/version -> target -> environment -> capability/action class -> decision/grant reference -> sandbox dispatch. Any failed stage returns a structured denial and performs no dispatch.

- [ ] **Step 4: Verify gateway**

```bash
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add security_gateway
git commit -m "feat: add Rust privileged execution gateway"
```

---

### Task 9: Sandbox backend probe and SOPHIA isolation selection

**Files:**
- Create: `security_gateway/src/sandbox/probe.rs`
- Create: `security_gateway/src/sandbox/kata.rs`
- Create: `security_gateway/src/sandbox/firecracker.rs`
- Create: `docs/superpowers/decisions/2026-09-23-stf-sandbox-selection.md`
- Test: `security_gateway/tests/sandbox_probe.rs`

**Interfaces:**
- Consumes: host capability evidence and `ExecutionEnvelope` already validated by the Rust gateway.
- Produces: exactly one selected `SandboxBackend` or `Unavailable`; no Docker/host fallback.

- [ ] **Step 1: Write fail-closed probe tests**

Test matrices: both unavailable -> `Unavailable`; only Kata supported -> `Kata`; only Firecracker supported -> `Firecracker`; configured backend unsupported -> startup failure; `auto` never selects an unsupported backend.

- [ ] **Step 2: Implement host probe inputs**

Probe facts include OS, architecture, KVM/device availability, runtime binary availability, required kernel features and configured network isolation support. Persist only probe results, not secrets.

- [ ] **Step 3: Implement backend interface**

```rust
pub trait SandboxBackend: Send + Sync {
    fn name(&self) -> &'static str;
    async fn execute(&self, request: SandboxRequest) -> Result<SandboxResult, SandboxError>;
    async fn terminate(&self, execution_id: &str) -> Result<(), SandboxError>;
}
```

Each backend receives an allowlisted `tool_id` and typed arguments; it does not expose an arbitrary command string API.

- [ ] **Step 4: Record SOPHIA selection from evidence**

Run the probe on the intended local host and record the facts and selected backend in the decision file. If the result is `Unavailable`, record privileged execution as blocked; do not weaken the boundary.

```bash
cargo test --test sandbox_probe
```

- [ ] **Step 5: Commit**

```bash
git add security_gateway/src/sandbox security_gateway/tests/sandbox_probe.rs docs/superpowers/decisions/2026-09-23-stf-sandbox-selection.md
git commit -m "feat: select fail closed isolated execution backend"
```

---

### Task 10: Evidence, Verification, Purple correlation and Chronicle integration

**Files:**
- Create: `backend/app/security_task_force/evidence.py`
- Create: `backend/app/security_task_force/verification.py`
- Modify: `backend/app/schemas/chronicle.py`
- Modify: `backend/app/repositories/domain.py`
- Test: `backend/tests/test_stf_evidence.py`
- Test: `backend/tests/test_stf_verification.py`

**Interfaces:**
- Consumes: Attack Evidence, Defense Evidence, action correlation ids and integrity hashes.
- Produces: `Finding` statuses `hypothesis`, `probable`, `confirmed`, `not_reproduced`, `rejected`; append-only Chronicle entries.

- [ ] **Step 1: Write verification invariant tests**

Prove: assertion without evidence cannot confirm; hash mismatch rejects evidence; Red finding requiring Purple correlation cannot confirm without Defense Evidence; replay that cannot reproduce becomes `not_reproduced`; confirmed finding writes Chronicle with evidence refs and policy/mission version.

- [ ] **Step 2: Run failing tests**

```bash
cd backend
pytest tests/test_stf_evidence.py tests/test_stf_verification.py -q
```

- [ ] **Step 3: Implement immutable evidence index and verification rules**

Verification accepts evidence references only when SHA-256, source, acquisition time, mission/action correlation and reproducibility metadata are present. Chronicle payload contains references/hashes, not secret-bearing raw evidence bodies.

- [ ] **Step 4: Verify Chronicle compatibility**

```bash
pytest tests/test_stf_evidence.py tests/test_stf_verification.py tests/test_system_event_cursor.py tests/test_postgres_integration.py -q
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/security_task_force/evidence.py backend/app/security_task_force/verification.py backend/app/schemas/chronicle.py backend/app/repositories/domain.py backend/tests/test_stf_evidence.py backend/tests/test_stf_verification.py
git commit -m "feat: verify security findings with linked evidence"
```

---

### Task 11: Canonicalize Cyber Range v1 without blind recreation

**Files:**
- Create or reconcile: `cyber_range/compose.yml`
- Create or reconcile: `cyber_range/controller/`
- Create or reconcile: `cyber_range/scenarios/`
- Create or reconcile: `cyber_range/scripts/start.sh`
- Create or reconcile: `cyber_range/scripts/stop.sh`
- Create or reconcile: `cyber_range/scripts/reset.sh`
- Create or reconcile: `cyber_range/scripts/verify.sh`
- Test: `cyber_range/tests/test_range_contract.py`
- Modify: `PROJECT_STATE.yaml`

**Interfaces:**
- Consumes: Task 1 reconciliation evidence.
- Produces: one canonical Range location containing the verified/ported v1 foundation, isolated vulnerable targets, scenario lifecycle and evidence hooks.

- [ ] **Step 1: Select source from Task 1 evidence**

If verified prior assets exist, port those exact assets into `cyber_range/` while preserving history in the audit. If the audit proves the reported assets absent, create the baseline in these same canonical paths and record that the recreation was evidence-triggered rather than memory-triggered.

- [ ] **Step 2: Write containment tests before enabling targets**

Tests assert vulnerable target services have no `0.0.0.0`/LAN port binding, controller accepts only declared scenario ids, reset removes scenario state, and evidence export goes only to the configured evidence directory/API.

- [ ] **Step 3: Add intentionally vulnerable targets only inside the isolated profile**

Use OWASP Juice Shop and WebGoat/WebWolf as training targets. Bind any host-published debugging ports to `127.0.0.1`; prefer internal-only Docker networks. Do not add external target scanning or uncontrolled egress.

- [ ] **Step 4: Verify lifecycle**

```bash
docker compose -f cyber_range/compose.yml config
./cyber_range/scripts/start.sh
./cyber_range/scripts/verify.sh
./cyber_range/scripts/reset.sh
./cyber_range/scripts/stop.sh
```

Expected: lifecycle commands succeed and no vulnerable service is reachable through a LAN-bound host port.

- [ ] **Step 5: Commit**

```bash
git add cyber_range PROJECT_STATE.yaml
git commit -m "feat: canonicalize isolated cyber range v1"
```

---

### Task 12: THE CREATION OS integration adapter and mission API

**Files:**
- Create: `backend/app/security_task_force/integration.py`
- Create: `backend/app/api/security_task_force.py`
- Modify: `backend/app/api/__init__.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/deus.py`
- Modify: `backend/app/schemas/mission.py`
- Test: `backend/tests/test_stf_integration_adapter.py`
- Test: `backend/tests/test_stf_api.py`

**Interfaces:**
- Consumes: Creator-authenticated natural-language intent through DEUS.
- Produces: mission compile request, mission status, escalation request, verified findings/evidence refs and completion/abort report; no unrestricted internal service access.

- [ ] **Step 1: Write integration boundary tests**

Assert DEUS can submit intent to the adapter but cannot directly invoke Rust Gateway; API cannot mark a finding confirmed; API cannot grant R3/R4 approval without Creator-authenticated approval reference; returned mission status maps from canonical STF state.

- [ ] **Step 2: Run failing tests**

```bash
cd backend
pytest tests/test_stf_integration_adapter.py tests/test_stf_api.py -q
```

- [ ] **Step 3: Implement explicit adapter**

Adapter methods:

```python
async def compile_intent(creator: Actor, intent: str, context: dict[str, Any]) -> CompiledMission: ...
async def get_mission_status(creator: Actor, mission_id: str) -> MissionStatusView: ...
async def submit_creator_approval(creator: Actor, action_id: str, decision: str) -> AuthorizationDecision: ...
async def cancel_mission(creator: Actor, mission_id: str, reason: str) -> None: ...
```

No method exposes database sessions, raw capability adapters or sandbox handles.

- [ ] **Step 4: Verify existing DEUS behavior remains green**

```bash
pytest tests/test_stf_integration_adapter.py tests/test_stf_api.py tests/test_deus_conversation.py tests/test_http_integration.py -q
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/security_task_force/integration.py backend/app/api backend/app/main.py backend/app/services/deus.py backend/app/schemas/mission.py backend/tests/test_stf_integration_adapter.py backend/tests/test_stf_api.py
git commit -m "feat: integrate security missions through explicit creation adapter"
```

---

### Task 13: Local Docker profiles, safe readiness, telemetry and runbooks

**Files:**
- Modify: `docker-compose.yml`
- Create: `deploy/stf/opa/`
- Create: `deploy/stf/temporal/`
- Create: `docs/runbooks/stf-start-stop.md`
- Create: `docs/runbooks/stf-kill-switch.md`
- Create: `docs/runbooks/stf-recovery.md`
- Create: `docs/runbooks/stf-evidence-integrity.md`
- Create: `backend/tests/test_stf_compose_invariants.py`

**Interfaces:**
- Consumes: implemented services from Tasks 5–12.
- Produces: `security-task-force` and `cyber-range` Compose profiles with isolated network zones and fail-closed readiness.

- [ ] **Step 1: Write compose invariant tests**

Parse Compose YAML and assert: Cyber Range services are profile-gated; vulnerable targets do not publish LAN ports; Rust gateway is not exposed publicly; API readiness for privileged execution depends on OPA, grant validation and sandbox control; Range profile is not required for ordinary frontend/API startup.

- [ ] **Step 2: Add control-plane services and networks**

Add NATS/JetStream, OPA and Temporal under `security-task-force`; add networks `creation-core`, `stf-control`, `stf-execution`, `cyber-range`, `observability`. Keep existing user-facing frontend port behavior unchanged unless explicitly required by current local topology.

- [ ] **Step 3: Add telemetry**

Emit structured mission/action/evidence ids and metrics for state transitions, authorization decisions, grant lifecycle, action latency/outcome, Temporal retries, NATS lag, sandbox lifecycle, evidence verification and kill-switch state. Secret values and raw capability tokens must be redacted.

- [ ] **Step 4: Verify configuration and runbooks**

```bash
docker compose config
cd backend && pytest tests/test_stf_compose_invariants.py tests/test_local_runtime_invariants.py tests/test_security_configuration.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml deploy/stf docs/runbooks backend/tests/test_stf_compose_invariants.py
git commit -m "feat: deploy security task force with isolated local profiles"
```

---

### Task 14: E2E, chaos, security gates and SH-X evidence specification

**Files:**
- Create: `backend/tests/test_stf_e2e_range.py`
- Create: `backend/tests/test_stf_chaos.py`
- Create: `backend/tests/test_stf_security_invariants.py`
- Create: `docs/security/shx-qualification.md`
- Create: `docs/superpowers/audits/2026-09-23-stf-release-evidence.md`
- Modify: `PROJECT_STATE.yaml`
- Modify: `CHANGELOG_DECISIONS.md`

**Interfaces:**
- Consumes: full implemented subsystem.
- Produces: reproducible release evidence and qualification criteria; status promotion only where evidence supports it.

- [ ] **Step 1: Add E2E Range scenario**

The E2E flow is exactly: reset Range -> start isolated target -> compile Range-bound mission -> authorize within R0-R2 -> execute only allowlisted validation action -> collect evidence -> Verification -> Chronicle -> teardown -> replay verification. Test must assert environment binding at every privileged action.

- [ ] **Step 2: Add chaos tests**

Inject worker restart, NATS interruption, OPA denial/unavailability, grant revocation during a mission, sandbox termination and evidence-store failure. Assertions: no unauthorized fallback, no duplicate state-changing action, mission transitions to paused/escalated/aborted as designed.

- [ ] **Step 3: Add security invariant tests**

Cover SSRF/egress policy boundary, path traversal in evidence references, action-parameter schema injection, capability-token replay, cross-target replay, cross-environment replay, expired/revoked grants, and secret redaction.

- [ ] **Step 4: Define evidence-based SH ladder**

`docs/security/shx-qualification.md` must define measurable scenario coverage, reproducibility percentage, policy-compliance requirement, evidence-integrity requirement, containment requirement and disqualifying failures for SH-1/2/3/X. Do not grant SH-X in this task unless the implemented test evidence satisfies those thresholds.

- [ ] **Step 5: Run full verification suite**

```bash
cd backend
pytest -q
ruff check app tests
mypy app
cd ../security_gateway
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test
cd ..
docker compose config
```

Then run the documented STF + Range integration profile and capture exact commands/results in `docs/superpowers/audits/2026-09-23-stf-release-evidence.md`.

- [ ] **Step 6: Promote statuses only from evidence and commit**

Update `PROJECT_STATE.yaml`: each component receives only the strongest evidenced status. `VERIFIED_OPERATIONAL` requires successful runtime evidence, not passing unit tests alone. Append the release evidence decision to `CHANGELOG_DECISIONS.md`.

```bash
git diff --check
git add backend/tests/test_stf_e2e_range.py backend/tests/test_stf_chaos.py backend/tests/test_stf_security_invariants.py docs/security/shx-qualification.md docs/superpowers/audits/2026-09-23-stf-release-evidence.md PROJECT_STATE.yaml CHANGELOG_DECISIONS.md
git commit -m "test: validate security task force release gates"
```

---

## Final self-review checklist

Before declaring implementation complete:

- [ ] Every Phase 3 contract field exists, including `authorized_environments`.
- [ ] Mission Compiler output is schema-valid, policy-valid, versioned and reproducibly verifiable; no deterministic-LLM assumption remains.
- [ ] Existing Mission/Capability/Chronicle code is adapted or explicitly superseded with evidence; no duplicate truth source exists.
- [ ] R0-R5 behavior matches frozen decisions.
- [ ] Range authority cannot execute in `REAL_AUTHORIZED`.
- [ ] R3/R4 require authenticated Creator approval reference.
- [ ] R5 creates a new mission.
- [ ] Capability grants are short-lived, revocable and mission-version-bound.
- [ ] OPA/identity/grant/gateway/sandbox failure denies privileged execution.
- [ ] Rust Gateway exposes no arbitrary host-shell execution path.
- [ ] Kata/Firecracker selection is evidence-based; unsupported hosts fail closed.
- [ ] Temporal replay/restart and outbox retry do not duplicate state-changing work.
- [ ] NATS events retain event/correlation/causation ids.
- [ ] Findings require linked reproducible evidence and Chronicle integrity metadata.
- [ ] Cyber Range is isolated from LAN by default.
- [ ] Kill switch revokes grants and prevents new dispatch.
- [ ] Full Python and Rust test/lint suites pass.
- [ ] Release evidence document contains exact commands and results.
- [ ] `PROJECT_STATE.yaml` and `CHANGELOG_DECISIONS.md` reflect evidence, not aspiration.

## Execution handoff

Execute this plan task-by-task on `feat/security-task-force-runtime` in an isolated worktree. Use **superpowers:subagent-driven-development** when available because authorization, orchestration, Rust isolation and evidence integrity are separable review boundaries where an unnoticed defect has high security impact. If subagents are unavailable, use **superpowers:executing-plans** and preserve the same task/commit gates.
