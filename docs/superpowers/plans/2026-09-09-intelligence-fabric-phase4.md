# Intelligence Fabric Phase 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose verified provider/model health in the authenticated dashboard without fake telemetry or secret leakage.

**Architecture:** Add a testable `app.inference.status` snapshot builder over the canonical router/registry, wire it through a protected `/api/v1/system/inference` route, then render the normalized snapshot in the existing React dashboard. Telemetry is read-only and performs health probes only, never inference.

**Tech Stack:** Python 3, FastAPI, Pydantic, existing inference router/registry, React/TypeScript, Vitest, Playwright, pytest, Ruff, mypy, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-09-intelligence-fabric-phase4-design.md`

## Global Constraints

- No secrets or prompts in telemetry.
- No provider discovery outside the canonical registry.
- No model capabilities inferred from names or marketing.
- No fake latency, token counts, uptime, providers, or health.
- Health endpoint is authenticated and read-only.
- Health probing must not execute inference.

---

### Task 1: Snapshot contract and builder

**Files:**
- Create: `backend/app/inference/status.py`
- Test: `backend/tests/test_inference_status.py`

**Interfaces:**
- `async build_inference_status(router: ModelRouter) -> InferenceStatusSnapshot`
- Snapshot includes configured provider registry entries, provider health, and registered model profiles.

- [ ] Write RED tests for healthy/unavailable providers and model evidence normalization.
- [ ] Verify RED.
- [ ] Implement minimal snapshot models/builder.
- [ ] Verify focused GREEN.
- [ ] Commit.

### Task 2: Safe configured/unconfigured service

**Files:**
- Modify: `backend/app/inference/status.py`
- Test: `backend/tests/test_inference_status.py`

**Interfaces:**
- `async configured_inference_status(provider_name: str, router_factory=build_model_router) -> InferenceStatusSnapshot`
- `fake`/empty/unsupported configuration returns `configured=false` without exposing bootstrap exception text.

- [ ] Write RED tests for fake/unconfigured and bootstrap failure redaction.
- [ ] Verify RED.
- [ ] Implement fail-safe status service.
- [ ] Verify focused GREEN.
- [ ] Commit.

### Task 3: Protected API route

**Files:**
- Create: `backend/app/api/inference_status.py`
- Modify: `backend/app/api/__init__.py`
- Test: `backend/tests/test_inference_status_api.py`

**Interfaces:**
- GET `/api/v1/system/inference`
- Uses existing `actor` authentication dependency.

- [ ] Write RED auth/response tests.
- [ ] Verify RED.
- [ ] Wire route to service.
- [ ] Verify focused GREEN.
- [ ] Commit.

### Task 4: Dashboard integration

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Test: existing frontend unit/E2E tests or new focused test if needed.

**Interfaces:**
- `fetchInferenceStatus(): Promise<InferenceStatusSnapshot>`
- Add `INFERENCE FABRIC` panel using verified fields only.

- [ ] Write/adjust frontend test for verified and unconfigured rendering.
- [ ] Verify RED.
- [ ] Implement typed fetch/rendering.
- [ ] Verify build/unit/E2E GREEN.
- [ ] Commit.

### Task 5: Full verification

- [ ] Run Ruff, mypy, Alembic and full pytest.
- [ ] Run frontend build, unit tests and Playwright E2E.
- [ ] Audit diff for secret leakage and fabricated telemetry.
- [ ] Open/update stacked PR against Phase 3 and mark ready only after fresh full CI success.
