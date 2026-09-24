# Security Task Force + Cyber Range — Codex Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved Security Task Force and Cyber Range architecture as a bounded, auditable subsystem integrated with THE CREATION OS without duplicating existing mission/capability primitives.

**Architecture:** Extend the existing Python mission and capability layers, add durable orchestration through Temporal, versioned events through NATS/JetStream, deterministic authorization through OPA, a Rust privileged-execution gateway, and an isolation controller selected by SOPHIA through a host-capability gate. Keep Cyber Range workloads isolated and reuse current Chronicle/capability/runtime code wherever repository evidence shows an equivalent responsibility already exists.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic 2, SQLAlchemy async, PostgreSQL/pgvector, Redis, Temporal, NATS/JetStream, OPA/Rego, Rust, Docker Compose, pytest/pytest-asyncio, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-23-security-task-force-cyber-range-design.md`

**Normative amendment:** `docs/superpowers/specs/2026-09-23-security-task-force-review-amendment.md`

## Global Constraints

- Repository evidence outranks conversational recollection.
- Do not redesign frozen decisions without an explicit superseding decision.
- Extend existing mission/capability code before introducing duplicate truth sources.
- `MissionContract` binds both `authorized_targets` and `authorized_environments`.
- Environment identifiers use explicit values such as `cyber_range:<scenario-or-zone>` and `real:<approved-environment-id>`.
- A capability/grant issued for one `environment_id` must fail closed in every other environment.
- Mission Compiler output may use AI internally but must be schema-valid, policy-valid, versioned, normalized, persisted and reproducibly verifiable.
- R3/R4 require Creator approval evidence; R5 creates a new mission.
- No ambient or permanent agent authority; capability grants are short-lived and mission/task/target/environment/action scoped.
- Privileged execution path remains Authorization Plane -> Rust Gateway -> isolated sandbox.
- SOPHIA selects Kata Containers or Firecracker only after host-capability evaluation. No weaker silent fallback is permitted.
- Cyber Range vulnerable targets are never exposed to LAN by default.
- Implementation branches/worktrees only; no direct implementation push to `main`.
- Every state-changing operation must be idempotent or explicitly at-most-once with persisted replay protection.

## Review Focus

1. A valid target with the wrong `environment_id` must be denied before privileged dispatch.
2. Expired/revoked grants and stale mission versions must fail closed across process restarts.
3. Duplicate idempotency keys must not repeat a state-changing external effect.
4. Loss of OPA, grant validation, Rust Gateway or sandbox control must make privileged execution unavailable, never permissive.
5. Host incompatibility with Kata/Firecracker must disable privileged execution while leaving control-plane and simulation functions available.

---

### Task 1: Reconciliation audit and implementation baseline

**Files:**
- Modify: `PROJECT_STATE.yaml`
- Create: `docs/superpowers/audits/2026-09-23-security-task-force-reconciliation.md`
- Read: `backend/app/schemas/mission.py`
- Read: `backend/app/capabilities/contracts.py`
- Read: `backend/app/capabilities/mission_authorization.py`
- Read: `backend/app/capabilities/gateway.py`
- Read: `backend/app/capabilities/runtime.py`
- Read: `backend/app/worker.py`
- Read: `docker-compose.yml`

**Interfaces:**
- Consumes: canonical state/spec/frozen decisions plus current repository code.
- Produces: a verified reuse map and an updated `PROJECT_STATE.yaml` implementation baseline.

- [ ] **Step 1: Create the reconciliation audit with evidence-backed rows**

Record each proposed component as `REUSE`, `EXTEND`, `CREATE`, or `VERIFY_HISTORY`. At minimum include Mission Authorization, Mission schemas, capability gateway/runtime, Chronicle/evidence storage, worker/orchestrator, Cyber Range v1, Docker topology, Temporal, NATS, OPA, Rust Gateway and sandbox controller.

- [ ] **Step 2: Verify historical Cyber Range claims across branches**

Run repository searches for `Range Controller`, `Juice Shop`, `WebGoat`, `WebWolf`, `qualification`, `evidence journal`, `cyber-range` and compare `main`, `feat/canonical-project-state`, and `fix/creator-interface-living-functional-scene`. Record exact paths/SHAs found; do not recreate absent components during this task.

- [ ] **Step 3: Run current baseline tests before modifications**

```bash
cd backend
pytest -q
ruff check app tests
mypy app
```

Expected: record actual pass/fail counts in the audit. Existing failures must be classified before feature work.

- [ ] **Step 4: Update canonical state**

Set repository-verified statuses in `PROJECT_STATE.yaml` without promoting any component beyond observed evidence.

- [ ] **Step 5: Commit**

```bash
git add PROJECT_STATE.yaml docs/superpowers/audits/2026-09-23-security-task-force-reconciliation.md
git commit -m "docs: reconcile security task force implementation baseline"
```

---

### Task 2: MissionContract, environment binding, and risk contracts

**Files:**
- Modify: `backend/app/schemas/mission.py`
- Modify: `backend/app/capabilities/contracts.py`
- Create: `backend/app/security_task_force/contracts.py`
- Create: `backend/tests/test_security_task_force_contracts.py`

**Interfaces:**
- Consumes: existing `MissionAuthorization`, `CapabilityIntent` and mission schemas.
- Produces: `MissionContract`, `ActionRequest`, `AuthorizationDecision`, `CapabilityGrant`, `EvidenceRecord`, `Finding`, `RiskClass`, `MissionState`.

- [ ] **Step 1: Write failing contract tests**

```python
from pydantic import ValidationError
import pytest

from app.security_task_force.contracts import MissionContract, RiskClass


def test_mission_contract_requires_authorized_environment():
    with pytest.raises(ValidationError):
        MissionContract(
            mission_id="m1",
            creator_id="c1",
            objective="validate",
            success_criteria=["verified"],
            authorized_targets=["target-1"],
            authorized_environments=[],
            excluded_targets=[],
            allowed_action_classes=["read"],
            risk_ceiling=RiskClass.R1,
            mission_version=1,
        )


def test_range_and_real_environments_are_explicit():
    contract = MissionContract(
        mission_id="m1",
        creator_id="c1",
        objective="validate",
        success_criteria=["verified"],
        authorized_targets=["target-1"],
        authorized_environments=["cyber_range:lab-a"],
        excluded_targets=[],
        allowed_action_classes=["read"],
        risk_ceiling=RiskClass.R1,
        mission_version=1,
    )
    assert contract.authorized_environments == ["cyber_range:lab-a"]
```

- [ ] **Step 2: Run the tests and verify failure**

```bash
cd backend
pytest tests/test_security_task_force_contracts.py -q
```

Expected: FAIL because `app.security_task_force.contracts` does not exist.

- [ ] **Step 3: Implement focused Pydantic contracts**

Create `backend/app/security_task_force/contracts.py` with enums `RiskClass(R0..R5)` and `MissionState(DRAFT..ABORTED)` plus the six contracts. `MissionContract` must reject empty `authorized_environments`, normalize duplicated target/environment values, and expose `normalized_payload()` returning a recursively key-sorted JSON-compatible dictionary used for canonical hashing.

- [ ] **Step 4: Extend current authorization schema without breaking callers**

Add `authorized_environments: list[str]`, `risk_class: RiskClass`, and optional `creator_approval_ref` to `MissionAuthorizationRequest`; retain current legacy fields during migration and map them explicitly in one compatibility function.

- [ ] **Step 5: Add environment mismatch test**

```python
def test_action_environment_must_match_grant():
    grant = make_grant(environment_id="cyber_range:lab-a")
    action = make_action(environment_id="real:prod-a")
    assert grant.matches(action) is False
```

- [ ] **Step 6: Run focused and existing mission/capability tests**

```bash
pytest tests/test_security_task_force_contracts.py tests/test_mission_plan_contracts.py tests/test_capability_gateway.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/mission.py backend/app/capabilities/contracts.py backend/app/security_task_force/contracts.py backend/tests/test_security_task_force_contracts.py
git commit -m "feat: add bounded mission and environment contracts"
```

---

### Task 3: Mission Compiler verification boundary

**Files:**
- Create: `backend/app/security_task_force/mission_compiler.py`
- Create: `backend/app/security_task_force/canonicalize.py`
- Create: `backend/tests/test_mission_compiler.py`
- Modify: `backend/app/services/deus.py`

**Interfaces:**
- Consumes: natural-language Creator intent plus structured context.
- Produces: persisted/verifiable `MissionContract` and `contract_hash`.

- [ ] **Step 1: Write failing tests for canonical verification**

```python
def test_semantically_identical_contract_payloads_hash_identically():
    a = canonical_hash({"b": 2, "a": 1})
    b = canonical_hash({"a": 1, "b": 2})
    assert a == b


def test_compiler_rejects_ambiguous_environment():
    result = compile_verified_contract(intent="check target", authorized_environments=[])
    assert result.status == "REJECTED"
    assert "environment" in result.reason_codes
```

- [ ] **Step 2: Verify tests fail**

```bash
pytest tests/test_mission_compiler.py -q
```

- [ ] **Step 3: Implement canonicalization**

Use UTF-8 JSON with sorted keys and compact separators, then SHA-256. Persist policy-version and compiler-version references with the contract. Do not test for identical model prose.

- [ ] **Step 4: Implement compiler boundary**

The compiler accepts a structured candidate from AI/reasoning, validates it through `MissionContract`, enforces required authority/target/environment fields, canonicalizes, hashes, and returns either `COMPILED` or `REJECTED` with reason codes.

- [ ] **Step 5: Integrate DEUS at the boundary only**

`DEUS` may invoke the compiler but may not issue privileged authorization. Preserve current conversation behavior while adding a mission-compilation path.

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_mission_compiler.py tests/test_deus_conversation.py -q
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/security_task_force/mission_compiler.py backend/app/security_task_force/canonicalize.py backend/app/services/deus.py backend/tests/test_mission_compiler.py
git commit -m "feat: add verifiable mission compiler boundary"
```

---

### Task 4: Authorization Plane, OPA policy, and ephemeral grants

**Files:**
- Modify: `backend/app/capabilities/mission_authorization.py`
- Create: `backend/app/security_task_force/authorization.py`
- Create: `deploy/opa/policies/mission.rego`
- Create: `deploy/opa/policies/mission_test.rego`
- Create: `backend/tests/test_security_task_force_authorization.py`

**Interfaces:**
- Consumes: `MissionContract`, `ActionRequest`, actor identity, target/environment metadata.
- Produces: `AuthorizationDecision` and short-lived `CapabilityGrant`.

- [ ] **Step 1: Write failing Python policy-envelope tests**

```python
async def test_r3_requires_creator_approval_ref():
    decision = await authorize(action=make_action(risk_class="R3"), mission=make_mission(), creator_approval_ref=None)
    assert decision.decision == "escalate"


async def test_wrong_environment_denied():
    decision = await authorize(action=make_action(environment_id="real:a"), mission=make_mission(environments=["cyber_range:a"]))
    assert decision.decision == "deny"
```

- [ ] **Step 2: Write Rego tests**

`mission_test.rego` must prove default deny, R3/R4 approval requirement, target/environment match, expiry enforcement, mission-version match, and R5 rejection as a same-mission action.

- [ ] **Step 3: Run tests and verify failure**

```bash
pytest tests/test_security_task_force_authorization.py -q
docker run --rm -v "$PWD/../deploy/opa/policies:/policies" openpolicyagent/opa:latest test /policies -v
```

- [ ] **Step 4: Implement Authorization Plane adapter**

Return only `permit`, `deny`, or `escalate`. A transport/policy error returns `deny` for privileged execution with reason `policy_unavailable`.

- [ ] **Step 5: Persist grant version/revocation semantics through current mission authorization path**

Extend `set_mission_authorization()` to store `authorized_environments`, `risk_class`, grant expiry and approval reference while retaining monotonically increasing authorization versions.

- [ ] **Step 6: Run capability regression suite**

```bash
pytest tests/test_security_task_force_authorization.py tests/test_capability_gateway.py tests/test_capability_runtime_integration.py tests/test_capability_failure_propagation.py -q
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/capabilities/mission_authorization.py backend/app/security_task_force/authorization.py deploy/opa/policies backend/tests/test_security_task_force_authorization.py
git commit -m "feat: enforce mission authorization and ephemeral grants"
```

---

### Task 5: Durable mission workflow with Temporal

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/app/security_task_force/workflows.py`
- Create: `backend/app/security_task_force/activities.py`
- Create: `backend/app/security_task_force/temporal_worker.py`
- Create: `backend/tests/test_security_task_force_workflow.py`

**Interfaces:**
- Consumes: compiled/authorized mission contract.
- Produces: durable state transitions DRAFT -> ... -> COMPLETED/ABORTED with cancellation, retry and compensation semantics.

- [ ] **Step 1: Add Temporal dependency**

Add `temporalio` with a bounded compatible version to `backend/pyproject.toml` and regenerate the project lock mechanism if the repository uses one.

- [ ] **Step 2: Write Temporal test-environment workflow tests**

Cover restart-safe progress, cancellation, R3 escalation wait, and no duplicate completion side effect after activity retry.

- [ ] **Step 3: Run and verify failure**

```bash
pytest tests/test_security_task_force_workflow.py -q
```

- [ ] **Step 4: Implement workflow**

Keep workflow code deterministic: no direct network/DB/model calls inside workflow methods. Put external operations in activities. State-changing activities require idempotency keys.

- [ ] **Step 5: Add kill-switch cancellation path**

A cancellation signal must prevent new dispatch and revoke/expire active grants through an activity before terminal transition.

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_security_task_force_workflow.py tests/test_cancellation_invariant.py tests/test_chaos_recovery.py -q
```

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml backend/app/security_task_force/workflows.py backend/app/security_task_force/activities.py backend/app/security_task_force/temporal_worker.py backend/tests/test_security_task_force_workflow.py
git commit -m "feat: add durable security mission workflow"
```

---

### Task 6: Versioned NATS/JetStream event transport

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/app/security_task_force/events.py`
- Create: `backend/app/security_task_force/event_bus.py`
- Create: `backend/tests/test_security_task_force_events.py`

**Interfaces:**
- Consumes: mission/action/evidence transitions.
- Produces: versioned events containing `event_id`, `schema_version`, timestamp, mission id, correlation id, causation id.

- [ ] **Step 1: Write failing schema tests**

Verify all event names in the Phase 4 namespace are accepted and unknown/unversioned names are rejected.

- [ ] **Step 2: Implement schemas**

Use Pydantic discriminated models or one envelope plus typed payload map. Require explicit `.v1` suffix.

- [ ] **Step 3: Implement JetStream adapter**

Publish with message id derived from `event_id`; configure durable consumers and observable dead-letter subject for poison messages.

- [ ] **Step 4: Test duplicate event publishing behavior**

Publishing the same `event_id` twice must not create two downstream state transitions.

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_security_task_force_events.py -q
```

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/app/security_task_force/events.py backend/app/security_task_force/event_bus.py backend/tests/test_security_task_force_events.py
git commit -m "feat: add versioned mission event bus"
```

---

### Task 7: Rust privileged execution gateway

**Files:**
- Create: `rust/security-gateway/Cargo.toml`
- Create: `rust/security-gateway/src/main.rs`
- Create: `rust/security-gateway/src/contracts.rs`
- Create: `rust/security-gateway/src/validation.rs`
- Create: `rust/security-gateway/tests/authorization.rs`

**Interfaces:**
- Consumes: signed/bound `CapabilityGrant`, `AuthorizationDecision`, `ActionRequest`.
- Produces: `GatewayDecision::Permit|Deny` and, only on permit, a sandbox dispatch request.

- [ ] **Step 1: Write Rust tests first**

Tests must deny expired grants, revoked grants, mission-version mismatch, target mismatch, environment mismatch, action-class mismatch, replayed invocation and missing policy decision.

- [ ] **Step 2: Run and verify failure**

```bash
cd rust/security-gateway
cargo test
```

- [ ] **Step 3: Implement pure validation core**

Validation order: parse -> integrity -> expiry/revocation -> mission/version -> target -> environment -> action class -> invocation/replay budget -> policy decision. Any failure returns a structured deny reason and never dispatches.

- [ ] **Step 4: Add replay store abstraction**

Define a trait for atomic replay/idempotency reservation; provide an in-memory test implementation and a production adapter boundary to persistent storage.

- [ ] **Step 5: Run quality gates**

```bash
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
```

- [ ] **Step 6: Commit**

```bash
git add rust/security-gateway
git commit -m "feat: add privileged Rust authorization gateway"
```

---

### Task 8: SOPHIA sandbox selection and host-capability gate

**Files:**
- Create: `backend/app/security_task_force/sandbox.py`
- Create: `backend/app/security_task_force/host_capabilities.py`
- Create: `backend/tests/test_sandbox_selection.py`
- Create: `docs/runbooks/sandbox-selection.md`

**Interfaces:**
- Consumes: host capability probe results and mission execution requirements.
- Produces: `SandboxSelection(engine, privileged_execution_enabled, reason_codes)`.

- [ ] **Step 1: Write failing selection tests**

```python
def test_no_supported_strong_isolation_disables_privileged_execution():
    result = select_sandbox(host=HostCapabilities(kata=False, firecracker=False))
    assert result.privileged_execution_enabled is False


def test_selection_never_falls_back_to_plain_docker():
    result = select_sandbox(host=HostCapabilities(kata=False, firecracker=False, docker=True))
    assert result.engine is None
```

- [ ] **Step 2: Implement host capability probes**

Probe OS/virtualization/backend prerequisites without mutating host configuration.

- [ ] **Step 3: Implement SOPHIA decision function**

Rank only Kata or Firecracker using isolation strength, host compatibility, performance, operational complexity, auditability, recovery and least privilege. Plain Docker is never an equivalent privileged sandbox fallback.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_sandbox_selection.py -q
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/security_task_force/sandbox.py backend/app/security_task_force/host_capabilities.py backend/tests/test_sandbox_selection.py docs/runbooks/sandbox-selection.md
git commit -m "feat: gate privileged execution on strong sandbox support"
```

---

### Task 9: Evidence, Verification and Chronicle correlation

**Files:**
- Create: `backend/app/security_task_force/evidence.py`
- Create: `backend/app/security_task_force/verification.py`
- Modify: `backend/app/schemas/chronicle.py`
- Create: `backend/tests/test_security_task_force_verification.py`

**Interfaces:**
- Consumes: Attack Evidence, Defense Evidence, mission/action/environment correlation ids.
- Produces: integrity-hashed `EvidenceRecord` and verified `Finding` states.

- [ ] **Step 1: Write failing verification tests**

A finding cannot become `confirmed` without reproducible evidence. Relevant offensive validation requiring Purple correlation must contain both attack and defense evidence references. Environment id must match the mission/action/grant chain.

- [ ] **Step 2: Implement evidence hashing**

Hash evidence payload or exported artifact bytes plus immutable metadata; routine logs must store references and hashes rather than secrets/raw sensitive bodies.

- [ ] **Step 3: Implement verification state machine**

Allowed statuses: `hypothesis`, `probable`, `confirmed`, `not_reproduced`, `rejected`. Confirmation requires policy-defined evidence completeness and reproducibility.

- [ ] **Step 4: Extend Chronicle schema**

Add mission/action/task/environment correlation and evidence integrity references while preserving existing consumers.

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_security_task_force_verification.py tests/test_memory_provenance_integration.py -q
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/security_task_force/evidence.py backend/app/security_task_force/verification.py backend/app/schemas/chronicle.py backend/tests/test_security_task_force_verification.py
git commit -m "feat: add evidence verification and Chronicle correlation"
```

---

### Task 10: Cyber Range reconciliation and safe scenario controller

**Files:**
- Create or Modify only after Task 1 evidence: `deploy/cyber-range/compose.yml`
- Create or Modify only after Task 1 evidence: `backend/app/security_task_force/range_controller.py`
- Create: `backend/tests/test_cyber_range_containment.py`
- Create: `docs/runbooks/cyber-range.md`

**Interfaces:**
- Consumes: authorized `cyber_range:*` mission environment.
- Produces: lifecycle operations `start`, `stop`, `reset`, `verify`, isolated scenario status and evidence export references.

- [ ] **Step 1: Reuse historical Range files when verified**

If Task 1 locates the existing v1 implementation, port/reconcile it rather than creating parallel Range services. Preserve source commit/path evidence in the audit.

- [ ] **Step 2: Write containment tests**

Tests/config checks must prove vulnerable targets are not published on `0.0.0.0`, have no direct LAN ingress, and live on an isolated Docker network. Controller must reject `real:*` environment ids.

- [ ] **Step 3: Implement or reconcile lifecycle controller**

Expose explicit `start/stop/reset/verify` operations and scenario catalog lookup. Controller cannot grant real-environment authority.

- [ ] **Step 4: Run containment verification**

```bash
pytest tests/test_cyber_range_containment.py -q
docker compose -f deploy/cyber-range/compose.yml config
```

Expected: no vulnerable service published to LAN interfaces.

- [ ] **Step 5: Commit**

```bash
git add deploy/cyber-range backend/app/security_task_force/range_controller.py backend/tests/test_cyber_range_containment.py docs/runbooks/cyber-range.md
git commit -m "feat: reconcile isolated cyber range controller"
```

---

### Task 11: THE CREATION OS integration adapter

**Files:**
- Create: `backend/app/security_task_force/integration.py`
- Modify: `backend/app/api/deus.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_security_task_force_integration.py`

**Interfaces:**
- Consumes from THE CREATION OS: Creator identity, DEUS intent, SOPHIA context, validated memory references.
- Produces to THE CREATION OS: mission status, escalation requests, verified findings, evidence references, completion/abort report.

- [ ] **Step 1: Write boundary tests**

Verify that the adapter can initiate mission compilation and read status but cannot bypass Authorization Plane to call the executor directly.

- [ ] **Step 2: Implement adapter**

Expose explicit methods such as `compile_mission`, `request_authorization`, `get_mission_status`, `cancel_mission`, `get_verified_findings`. Do not expose unrestricted repository/session handles.

- [ ] **Step 3: Add API integration route through DEUS**

Keep normal conversation behavior intact; mission initiation is an explicit path/action with authenticated Creator identity.

- [ ] **Step 4: Run HTTP and service regressions**

```bash
pytest tests/test_security_task_force_integration.py tests/test_deus_conversation.py tests/test_http_integration.py tests/test_services.py -q
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/security_task_force/integration.py backend/app/api/deus.py backend/app/main.py backend/tests/test_security_task_force_integration.py
git commit -m "feat: integrate security task force through explicit adapter"
```

---

### Task 12: Docker profiles, safe readiness, observability and runbooks

**Files:**
- Modify: `docker-compose.yml`
- Create: `deploy/security-task-force/compose.override.yml`
- Create: `docs/runbooks/security-task-force.md`
- Create: `docs/runbooks/global-kill-switch.md`
- Create: `docs/runbooks/authorization-failures.md`
- Create: `backend/tests/test_security_task_force_runtime_invariants.py`

**Interfaces:**
- Produces profiles `security-task-force`, `cyber-range`, optional `observability`; network zones and health/readiness behavior.

- [ ] **Step 1: Write runtime invariant tests**

Parse compose configuration and assert Range is not required for core startup, vulnerable ports are not LAN-bound, OPA/Temporal/NATS dependencies gate privileged readiness, and ordinary API/frontend startup remains available when privileged execution is disabled.

- [ ] **Step 2: Extend compose**

Add Temporal, NATS/JetStream and OPA in `security-task-force`; isolate Range in its own profile/network. Do not expose OPA/NATS/Temporal publicly unless a documented local-only port is needed for diagnostics.

- [ ] **Step 3: Add structured telemetry**

Instrument mission transitions, authorization decisions, grant lifecycle, action outcome, Temporal retry/failure, NATS lag, sandbox lifecycle, evidence verification, kill-switch state and Range scenario result with mission/action/evidence correlation ids.

- [ ] **Step 4: Add runbooks**

Document startup/shutdown, grant revocation, global kill switch, Temporal recovery, NATS drain, Chronicle integrity verification, credential rotation, backup/restore, authorization failure and sandbox failure.

- [ ] **Step 5: Verify compose and tests**

```bash
docker compose config
pytest tests/test_security_task_force_runtime_invariants.py tests/test_local_runtime_invariants.py tests/test_release_invariants.py -q
```

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml deploy/security-task-force docs/runbooks backend/tests/test_security_task_force_runtime_invariants.py
git commit -m "feat: add safe local security task force runtime profiles"
```

---

### Task 13: Full E2E, chaos, security and release gates

**Files:**
- Create: `backend/tests/test_security_task_force_e2e.py`
- Create: `backend/tests/test_security_task_force_chaos.py`
- Create: `backend/tests/test_security_task_force_security.py`
- Modify: `PROJECT_STATE.yaml`
- Modify: `CHANGELOG_DECISIONS.md` only if implementation reveals a real design supersession.

**Interfaces:**
- Consumes: complete subsystem.
- Produces: evidence for `TESTED` / `VERIFIED_OPERATIONAL` status where justified.

- [ ] **Step 1: E2E Range scenario**

Run: reset Range -> start isolated target -> compile mission -> authorize Range environment -> dispatch allowed action -> collect attack/defense evidence -> verify finding -> Chronicle record -> teardown -> replay reproduction. Assert environment/target correlation across the full chain.

- [ ] **Step 2: Approval gate E2E**

Prove R3/R4 cannot execute without explicit Creator approval reference and R5 compiles a new mission rather than mutating scope.

- [ ] **Step 3: Chaos tests**

Kill/restart Temporal worker, restart NATS, deny OPA, revoke a grant mid-task, terminate sandbox, and simulate evidence-store failure. Assert no unauthorized continuation and no duplicate state-changing action.

- [ ] **Step 4: Security tests**

Exercise replay resistance, SSRF/egress policy, path traversal/action parameter validation, secret redaction, environment mismatch and cross-target grant reuse.

- [ ] **Step 5: Run full quality gate**

```bash
cd backend
pytest -q
ruff check app tests
mypy app
cd ../rust/security-gateway
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
cd ../..
docker compose config
```

Expected: all required suites pass. Any skipped external/real-provider test must have an explicit documented reason and must not be counted as operational evidence.

- [ ] **Step 6: Update canonical status from evidence only**

Promote each component separately from `IMPLEMENTED` to `TESTED` or `VERIFIED_OPERATIONAL` only when the corresponding test/runtime evidence exists. Do not mark real-environment execution verified merely because Cyber Range tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/tests/test_security_task_force_e2e.py backend/tests/test_security_task_force_chaos.py backend/tests/test_security_task_force_security.py PROJECT_STATE.yaml CHANGELOG_DECISIONS.md
git commit -m "test: verify security task force release gates"
```

---

### Task 14: SH-X qualification specification and evidence-only certification

**Files:**
- Create: `docs/security/SHX_QUALIFICATION.md`
- Create: `backend/app/security_task_force/qualification.py`
- Create: `backend/tests/test_shx_qualification.py`

**Interfaces:**
- Consumes: scenario results, containment results, policy compliance, evidence reproducibility and release-gate records.
- Produces: internal qualification result only; never external accreditation claims.

- [ ] **Step 1: Define explicit rubric before scoring code**

Define required scenario families, mandatory containment gates, reproducibility requirements, policy-compliance gates and evidence-completeness gates. Any mandatory containment or authorization failure must make SH-X ineligible regardless of aggregate score.

- [ ] **Step 2: Write qualification tests**

Prove that high scenario performance cannot compensate for a failed containment gate, missing R3/R4 approval test, unverified evidence chain or unreproduced required scenario.

- [ ] **Step 3: Implement evaluator**

Evaluator consumes immutable test/evidence references and returns `eligible: bool`, passed/failed gates and evidence references. It never self-generates evidence.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_shx_qualification.py -q
```

- [ ] **Step 5: Commit**

```bash
git add docs/security/SHX_QUALIFICATION.md backend/app/security_task_force/qualification.py backend/tests/test_shx_qualification.py
git commit -m "feat: add evidence-based SH-X qualification gates"
```

---

## Final verification before merge

- [ ] Read `CONTEXT_BOOTSTRAP.md`, `PROJECT_STATE.yaml`, `FROZEN_DECISIONS.md`, `ARCHITECTURE_GRAPH.yaml`, `CHANGELOG_DECISIONS.md`, the design spec and normative amendment again.
- [ ] Confirm no implementation silently superseded a frozen decision.
- [ ] Confirm `authorized_environments` flows through MissionContract -> ActionRequest -> AuthorizationDecision -> CapabilityGrant -> Rust Gateway -> EvidenceRecord/Chronicle.
- [ ] Confirm no real-environment permission is implied by Cyber Range success.
- [ ] Confirm no plain-Docker privileged sandbox fallback exists.
- [ ] Confirm default-deny behavior during OPA/identity/grant/gateway/sandbox failure.
- [ ] Confirm all release commands pass and retain logs/artifacts needed for review.
- [ ] Request Superpowers code review before merge.

## Execution handoff

Implementation should begin from a dedicated worktree/feature branch created from the reconciled current baseline. The recommended execution method is **subagent-driven development**, because the plan spans Python contracts/policy/workflows, Rust privileged execution, container isolation, infrastructure, evidence verification and security testing; each task has a meaningful independent review boundary and mistakes at authorization/isolation boundaries have high cost.
