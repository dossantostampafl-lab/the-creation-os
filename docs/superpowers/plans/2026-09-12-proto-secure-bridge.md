# PROTO Secure Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire THE CREATION OS to PROTO's existing authenticated safe Creation bridge with a narrow, testable capability adapter and fail-closed production configuration.

**Architecture:** Add one `ProtoCapabilityAdapter` behind the existing `CapabilityGateway`. The worker registers it only when fixed process configuration is complete; the adapter maps a governed `CapabilityIntent` to PROTO Mission v1 and validates that PROTO never claims financial connectivity or real-money execution through this bridge.

**Tech Stack:** Python 3.12+, Pydantic, httpx, FastAPI-era settings, pytest/pytest-asyncio, existing CapabilityRuntime.

**Spec:** `docs/superpowers/specs/2026-09-12-proto-secure-bridge-design.md`

## Global Constraints
- PROTO base URL is process configuration only; agents cannot choose hosts.
- Production PROTO URL must use HTTPS.
- Shared secret is a `SecretStr` and is never persisted in capability request/result/error JSON.
- Allowed PROTO jobs are exactly `market-data-health`, `opportunity-scan`, `shadow-decision`.
- Financial live modes are rejected by the Creation adapter.
- No automatic retry of POST mission submission.
- Existing CapabilityRuntime authorization and invocation persistence remain unchanged.

---

### Task 1: Configuration contract

**Files:**
- Modify: `backend/app/config.py`
- Modify: `.env.example`
- Test: `backend/tests/test_proto_adapter.py`

**Interfaces:**
- Produces: `settings.proto_base_url`, `settings.proto_creation_shared_secret`, `settings.proto_timeout_seconds`, `settings.proto_bridge_configured`.

- [ ] **Step 1: Write failing configuration tests**

```python
def test_proto_bridge_requires_url_and_secret(monkeypatch):
    ...

def test_proto_bridge_rejects_http_in_production(monkeypatch):
    ...
```

- [ ] **Step 2: Run focused test and verify RED**

Run: `pytest backend/tests/test_proto_adapter.py -q`
Expected: FAIL because PROTO settings do not exist.

- [ ] **Step 3: Add settings and environment documentation**

Add optional `PROTO_BASE_URL`, optional `PROTO_CREATION_SHARED_SECRET: SecretStr`, positive `PROTO_TIMEOUT_SECONDS=10`, and a computed `proto_bridge_configured` property. Validate HTTPS when `APP_ENV=production` and URL is configured.

- [ ] **Step 4: Run focused tests**

Run: `pytest backend/tests/test_proto_adapter.py -q`
Expected: configuration tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_proto_adapter.py .env.example
git commit -m "feat(integration): configure secure PROTO bridge"
```

### Task 2: PROTO capability adapter

**Files:**
- Create: `backend/app/capabilities/proto.py`
- Test: `backend/tests/test_proto_adapter.py`

**Interfaces:**
- Consumes: `CapabilityIntent`, `CapabilityResult`, fixed PROTO configuration.
- Produces: `ProtoCapabilityAdapter.execute(intent) -> CapabilityResult`.

- [ ] **Step 1: Add failing adapter tests**

Cover exact URL `/creation/missions`, `X-Proto-Creation-Token`, Mission v1 payload, safe job allowlist, safe modes, caller URL/token rejection, timeout/network failure sanitization, and financial invariant validation.

- [ ] **Step 2: Run focused test and verify RED**

Run: `pytest backend/tests/test_proto_adapter.py -q`
Expected: FAIL because `ProtoCapabilityAdapter` does not exist.

- [ ] **Step 3: Implement minimal adapter**

Use `httpx.AsyncClient(timeout=..., follow_redirects=False)`. Accept only `capability="proto"`, `action="submit_mission"`; validate arguments locally; submit one POST; call `raise_for_status`; parse JSON; require `financial_connectivity is False` and `real_money_execution is False`; return sanitized `CapabilityResult`.

- [ ] **Step 4: Run focused tests**

Run: `pytest backend/tests/test_proto_adapter.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/capabilities/proto.py backend/tests/test_proto_adapter.py
git commit -m "feat(integration): add governed PROTO capability adapter"
```

### Task 3: Worker registration

**Files:**
- Modify: `backend/app/worker.py`
- Test: `backend/tests/test_proto_adapter.py`

**Interfaces:**
- Produces: helper `build_capability_gateway() -> CapabilityGateway` used by `run_worker()`.

- [ ] **Step 1: Add failing registration tests**

Prove adapter is absent when configuration is incomplete and registered exactly once when complete.

- [ ] **Step 2: Run focused test and verify RED**

Run: `pytest backend/tests/test_proto_adapter.py -q`
Expected: FAIL because registration helper does not exist.

- [ ] **Step 3: Implement registration helper**

Construct `CapabilityGateway`; if `settings.proto_bridge_configured`, register `ProtoCapabilityAdapter` with fixed settings; return gateway. Replace direct `CapabilityGateway()` creation in `run_worker()`.

- [ ] **Step 4: Run focused tests**

Run: `pytest backend/tests/test_proto_adapter.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/worker.py backend/tests/test_proto_adapter.py
git commit -m "feat(worker): wire PROTO bridge adapter"
```

### Task 4: Release and security invariants

**Files:**
- Modify: `backend/tests/test_release_gate.py`
- Modify: `README.md`

**Interfaces:**
- Produces: deterministic release assertions that production cannot silently configure an insecure PROTO bridge.

- [ ] **Step 1: Add failing release-gate assertions**

Assert documented variables exist and production configuration with PROTO enabled requires HTTPS plus a secret.

- [ ] **Step 2: Run release tests and verify RED**

Run: `pytest backend/tests/test_release_gate.py -q`
Expected: FAIL until docs/config are aligned.

- [ ] **Step 3: Document operational contract**

Document `PROTO_BASE_URL`, `PROTO_CREATION_SHARED_SECRET`, safe-job scope, and explicit no-financial-execution boundary.

- [ ] **Step 4: Run release tests**

Run: `pytest backend/tests/test_release_gate.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_release_gate.py README.md
git commit -m "docs(release): define PROTO bridge production boundary"
```

### Task 5: Full verification and PR review

**Files:**
- Review all changed files.

**Interfaces:**
- Produces: merge-ready PR only if deterministic CI and Security are green.

- [ ] **Step 1: Run backend verification**

Run: `ruff check app tests && mypy app && alembic upgrade head && pytest`
Expected: all PASS (existing intentional skip permitted).

- [ ] **Step 2: Run project CI/security workflows via PR**

Open a draft PR from `integration/proto-secure-bridge` to `main`; require CI and Security SUCCESS.

- [ ] **Step 3: Review diff**

Verify no secret is logged/persisted, no arbitrary URL path exists, no financial/live job enters the local allowlist, and no unrelated refactor was introduced.

- [ ] **Step 4: Resolve failures using systematic debugging**

For each failing job, inspect exact logs, fix root cause, and rerun until green or a genuine external blocker is proven.

- [ ] **Step 5: Finalize branch**

Use verification-before-completion and finishing-a-development-branch. Do not represent PROTO production deployment as verified while its external Production Orchestration Contract is red.
