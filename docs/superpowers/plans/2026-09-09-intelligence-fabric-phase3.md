# Intelligence Fabric Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

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

**Files:**
- Modify: `backend/app/inference/contracts.py`
- Modify: `backend/app/inference/registry.py`
- Test: `backend/tests/test_inference_resilience.py`

**Interfaces:**
- Produces `CostTier` ordered policy enum/classes and `ModelRequirements.max_cost_tier`.
- Extends `ProviderModelProfile` with Creation-owned cost evidence defaulting to unknown.

- [ ] **Step 1: Write failing tests** proving an explicit cost ceiling rejects unknown/over-budget profiles and admits an in-budget profile.
- [ ] **Step 2: Run** `pytest backend/tests/test_inference_resilience.py -q` and record RED.
- [ ] **Step 3: Implement minimal contracts/profile changes** without assigning invented dollar prices.
- [ ] **Step 4: Run the focused tests** and obtain GREEN.
- [ ] **Step 5: Commit** `feat(inference): add budget admission evidence`.

### Task 2: Provider circuit breaker

**Files:**
- Create: `backend/app/inference/health.py`
- Test: `backend/tests/test_inference_resilience.py`

**Interfaces:**
- Produces `CircuitState`, `ProviderCircuitBreaker.can_attempt(provider, now)`, `record_success(provider)`, and `record_transient_failure(provider, now)`.
- State is per provider and in-memory in Phase 3.

- [ ] **Step 1: Write failing tests** for CLOSED -> OPEN -> HALF_OPEN -> CLOSED and HALF_OPEN -> OPEN transitions.
- [ ] **Step 2: Run focused tests** and record RED.
- [ ] **Step 3: Implement the minimal deterministic breaker**, with injectable/current monotonic time boundary suitable for tests.
- [ ] **Step 4: Run focused tests** and obtain GREEN.
- [ ] **Step 5: Commit** `feat(inference): add provider circuit breaker`.

### Task 3: Rate-limit cooldown

**Files:**
- Modify: `backend/app/inference/health.py`
- Test: `backend/tests/test_inference_resilience.py`

**Interfaces:**
- Produces cooldown registration/query methods scoped by provider.

- [ ] **Step 1: Write failing tests** proving a rate-limited provider is skipped during cooldown and eligible after expiry.
- [ ] **Step 2: Run focused tests** and record RED.
- [ ] **Step 3: Implement minimal cooldown state** without persisting credentials or response bodies.
- [ ] **Step 4: Run focused tests** and obtain GREEN.
- [ ] **Step 5: Commit** `feat(inference): add rate limit cooldown`.

### Task 4: Cause-aware router integration

**Files:**
- Modify: `backend/app/inference/router.py`
- Modify only if normalization evidence requires it: existing adapter/error contract files.
- Test: `backend/tests/test_inference_resilience.py`

**Interfaces:**
- Consumes Phase 2 capability profiles, Task 1 budget evidence, and Tasks 2-3 provider health.
- Preserves the existing public router request/result contract except for additive requirements.

- [ ] **Step 1: Write failing tests** for 429/rate-limit fallback, timeout/transient fallback, open-circuit skip, auth/config fail-closed, budget fail-closed, and unrelated-provider non-selection.
- [ ] **Step 2: Run focused tests** and record RED.
- [ ] **Step 3: Implement minimal routing integration**. Do not broaden candidate discovery.
- [ ] **Step 4: Run focused and existing inference tests** and obtain GREEN.
- [ ] **Step 5: Commit** `feat(inference): add cause aware resilient routing`.

### Task 5: Bootstrap conservative cost evidence

**Files:**
- Modify: `backend/app/inference/bootstrap.py`
- Test: `backend/tests/test_inference_resilience.py`

**Interfaces:**
- Existing configured profiles may receive only policy tiers that are supported by project configuration/evidence. If no reliable evidence exists, retain `UNKNOWN` rather than guessing.

- [ ] **Step 1: Write failing bootstrap tests** for the intended explicit evidence behavior.
- [ ] **Step 2: Run focused tests** and record RED.
- [ ] **Step 3: Implement the minimal bootstrap change**; do not infer provider pricing from model names.
- [ ] **Step 4: Run focused tests** and obtain GREEN.
- [ ] **Step 5: Commit** `feat(inference): bootstrap conservative budget evidence`.

### Task 6: Full verification and diff audit

**Files:**
- No feature expansion.
- Update PR description only after evidence exists.

- [ ] **Step 1: Run backend gate** equivalent to CI: dependency install as needed, `ruff check .`, `mypy app`, `python -m alembic upgrade head`, `pytest` from `backend`.
- [ ] **Step 2: Run frontend gate** equivalent to CI: install, build, unit tests, Playwright E2E.
- [ ] **Step 3: Audit branch diff** for implicit provider discovery, auth fallback, capability/budget bypass, secret leakage, fake telemetry, or tool-call enablement.
- [ ] **Step 4: Correct any finding using RED -> GREEN** and rerun the complete affected gate.
- [ ] **Step 5: Open/update stacked PR against `feat/intelligence-fabric-phase2` and claim readiness only after fresh complete CI success.**
