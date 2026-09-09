# Intelligence Fabric Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add Creation-owned budget admission, circuit breaking, rate-limit cooldown, and cause-aware fallback to the existing inference runtime without weakening explicit provider governance.

**Architecture:** `ModelRouter` stays canonical and composes small policy/health components. Provider adapters normalize provider failures; Creation decides whether a failure may advance to the next explicitly authorized candidate. Budget and health are admission gates, never provider-discovery mechanisms.

**Tech Stack:** Python 3, dataclasses/enums, existing inference adapters/registry/router, pytest, Ruff, mypy, Alembic, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-09-intelligence-fabric-phase3-design.md`

## Global Constraints

- No automatic provider discovery.
- No implicit fallback.
- Candidate order is only preferred provider plus explicit fallback providers.
- Budget/capability rejection cannot be bypassed by fallback.
- Authentication/authorization/configuration errors fail closed.
- Only normalized transient provider failures are fallback-eligible.
- No tool-call execution is enabled.
- No secrets or fake production telemetry.

---

### Task 1: Budget admission contracts

- [x] Write RED tests for explicit cost ceilings.
- [x] Verify RED.
- [x] Implement `CostTier`, `max_cost_tier`, profile cost evidence and `InferenceBudgetError`.
- [x] Verify focused GREEN.
- [x] Commit implementation.

### Task 2: Provider circuit breaker

- [x] Write RED tests for CLOSED -> OPEN -> HALF_OPEN transitions and half-open recovery/reopen.
- [x] Verify RED.
- [x] Implement deterministic in-memory per-provider breaker.
- [x] Verify focused GREEN.
- [x] Commit implementation.

### Task 3: Rate-limit cooldown

- [x] Write RED tests for scoped provider cooldown and expiry.
- [x] Verify RED.
- [x] Implement provider-scoped cooldown state.
- [x] Verify focused GREEN.
- [x] Commit implementation.

### Task 4: Cause-aware router integration

- [x] Write tests for rate-limit/timeout/transient fallback, open-circuit skip, auth/config fail-closed, budget fail-closed and unrelated-provider exclusion.
- [x] Verify RED where behavior was absent.
- [x] Integrate health and budget gates into `ModelRouter` without broadening candidate discovery.
- [x] Correct capability fallback semantics to fail closed when governance evidence rejects the preferred candidate.
- [x] Verify inference and full suite GREEN.

### Task 5: Bootstrap conservative cost evidence

- [x] Add bootstrap assertion that configured FreeLLMAPI profiles remain `CostTier.UNKNOWN` unless explicit evidence exists.
- [x] Preserve conservative bootstrap behavior rather than inventing pricing from provider/model names.
- [x] Verify test and full suite GREEN.

### Task 6: Full verification and diff audit

- [x] Backend CI gate: Ruff, mypy, Alembic and pytest.
- [x] Frontend CI gate: build, unit tests and Playwright E2E.
- [x] Audit diff for implicit provider discovery, auth fallback, capability/budget bypass, secret leakage, fake telemetry and tool-call enablement.
- [x] Correct findings through test-backed changes.
- [x] Final CI #199: backend and frontend success; pytest reported 165 passed.

## Verification Evidence

Final Phase 3 head before this documentation-only reconciliation: `543559eb32aafa210cae974e910b3d3b6ad3597b`.
GitHub Actions run #199 completed successfully for both backend and frontend. Backend evidence: Ruff passed, mypy reported no issues in 83 source files, Alembic upgraded through `0008_memory_provenance`, and pytest reported `165 passed`. Frontend build, unit tests and Playwright E2E passed.
