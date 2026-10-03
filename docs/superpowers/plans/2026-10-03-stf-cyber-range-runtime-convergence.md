# STF/Cyber Range Runtime Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the runtime gaps already identified in STF/Cyber Range while preserving the approved architecture and fail-closed safety model.

**Architecture:** Converge live run authority on StfRepository/PostgreSQL first, then connect isolated execution, evidence/verification, and qualification. File-backed stores remain compatibility-only until each runtime path is migrated.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/PostgreSQL, Temporal, OPA, Rust gateway, Docker Compose, pytest, cargo.

**Spec:** docs/superpowers/specs/2026-10-03-stf-cyber-range-runtime-convergence-design.md

## Global Constraints
- Cyber Range training remains isolated from production.
- No real:* execution path is added.
- No Docker socket and no plain-Docker privileged fallback.
- Stateful dispatch is at-most-once; unknown outcomes are never automatically replayed.
- TDD and Gauntlet loop apply to every task.

## Review Focus
- Cancellation racing a dispatch must never leave post-cancel authority.
- A replayed/duplicate action must not spend a second grant.
- DB/Chronicle failure must roll back authority.
- Lost gateway replies must become unknown, never automatic replay.
- Evidence from another run/action/environment must never complete or qualify a mission.

---

### Task 1: Canonical transactional dispatch authority

**Files:**
- Modify: backend/app/security_task_force/activities.py
- Modify: backend/app/security_task_force/authorization.py
- Modify: backend/app/security_task_force/temporal_worker.py
- Test: backend/tests/test_stf_activities.py
- Test: backend/tests/test_stf_repository.py
- Test: backend/tests/test_stf_workflow.py

**Interfaces:**
- Consumes: StfRepository.reserve_dispatch(run_id, ActionRequest, grant_id) -> DispatchReceipt
- Produces: stf_dispatch_action(..., run_id) using DB authority for live runs.

- [ ] RED: add tests proving a run_id dispatch must call reserve_dispatch and cannot use file-backed ledger/grant consumption.
- [ ] GREEN: route run_id authorization/grant issuance and dispatch reservation through StfRepository.
- [ ] Persist gateway outcome with record_outcome().
- [ ] Preserve legacy file-only path only when run_id is absent.
- [ ] Run STF unit + integration tests.
- [ ] Audit concurrency, cancellation, idempotency.
- [ ] Attack with duplicate/replay/cancel/Chronicle-failure cases.
- [ ] Fix findings and retest.

### Task 2: Isolated executor adapter

**Files:**
- Modify: security_gateway/src/sandbox/*
- Modify: security_gateway/src/server.rs
- Test: security_gateway/tests/*

**Interfaces:**
- Consumes: reserved execution claim + allowlisted tool_id.
- Produces: execution_id only when work actually ran.

- [ ] Add RED tests for a safe Cyber Range-only executor capability.
- [ ] Implement minimal isolated adapter; no real:* targets.
- [ ] Verify unavailable isolation fails closed.
- [ ] Red-Team allowlist bypass, replay, parameter tamper, environment forgery.

### Task 3: STF ↔ Cyber Range lifecycle integration

**Files:**
- Modify: backend/app/security_task_force/range_controller.py
- Modify: backend/app/security_task_force/activities.py
- Test: backend/tests/test_stf_e2e.py
- Test: cyber_range/tests/*

- [ ] Add capability contract for range scenario start/verify/reset.
- [ ] Route all through authorized worker/gateway path.
- [ ] Keep RangeController refusal of non-cyber_range:*.
- [ ] Validate reset/stop on cancellation.

### Task 4: Durable evidence and verification

**Files:**
- Modify: backend/app/models/security_task_force.py
- Add migration.
- Modify: backend/app/security_task_force/evidence.py
- Modify: backend/app/security_task_force/verification.py
- Modify: backend/app/security_task_force/activities.py
- Test: backend/tests/test_stf_e2e.py
- Test: backend/tests/test_stf_security_invariants.py

- [ ] Persist attack/defense evidence references with immutable correlation fields.
- [ ] Verify hash/correlation/reproduction before confirmed finding.
- [ ] Inject verifier into production worker.
- [ ] Mission cannot reach COMPLETED without verified evidence.

### Task 5: Chronicle + findings projection

- [ ] Publish verified finding references, not raw secret-bearing payloads.
- [ ] Project confirmed findings to Creator-facing status.
- [ ] Preserve redaction and tamper evidence.

### Task 6: Qualification feed

- [ ] Derive GateResult from persisted verified evidence.
- [ ] Feed qualification.evaluate() automatically.
- [ ] Keep SH disqualifiers fail-closed.
- [ ] Add regression tests for false SH-X claims.

### Task 7: Scenario and campaign depth

- [ ] Introduce versioned scenario manifests with objectives, prerequisites, success/failure criteria and deterministic reset.
- [ ] Add campaign orchestration across declared Range scenarios.
- [ ] Add Blue/Purple evidence and replay.
- [ ] Add blind/variant scenarios only after Tasks 1-6 are green.

### Task 8: Range containment hardening

- [ ] Add explicit host/egress-deny enforcement suitable for disposable range runners.
- [ ] Test that targets cannot reach unauthorized host/routed destinations.
- [ ] Keep loopback publication and no Docker socket.

### Final Gauntlet
- [ ] Full Python STF suite.
- [ ] PostgreSQL integration suite.
- [ ] Rust gateway fmt/clippy/test.
- [ ] OPA check/test.
- [ ] Cyber Range contract + runtime smoke.
- [ ] Security workflows.
- [ ] Whole-branch audit and Red Team pass.
- [ ] Fix Critical/Important findings.
- [ ] Re-run all gates before merge.


## Gauntlet Progress

### Task 1 — COMPLETE
Verified on branch HEAD lineage through `845049b`:
- persisted runs authorize from PostgreSQL contracts;
- grants are persisted only for active matching runs;
- `reserve_dispatch()` is the canonical authority before gateway dispatch;
- gateway outcomes are persisted with `record_outcome()`;
- legacy file stores are not the authority for persisted dispatch;
- replay, cancellation, lost-response/unknown and Chronicle rollback attacks are covered;
- Security Task Force, Security and full CI (PostgreSQL, mypy, Alembic, pytest) passed.

### Ruling before Task 2
**Ruling:** A Cyber Range controller health/lifecycle call through the authenticated, fixed-destination Range control relay is control-plane activity, not privileged code execution. It may be executed after the Rust Gateway validates the signed Mission envelope, even when Kata/Firecracker are unavailable. Any capability that executes commands/tools/processes remains disabled unless a strong isolation backend is proven available by `deploy/stf/verify-host.sh`. No plain-Docker fallback is introduced.

**Cost if wrong:** Misclassifying a future capability as range-control could bypass the strong-sandbox requirement. Therefore the gateway must use an exact tool allowlist and fixed controller routes; unknown tools continue through the strong sandbox path and fail closed when it is unavailable.
