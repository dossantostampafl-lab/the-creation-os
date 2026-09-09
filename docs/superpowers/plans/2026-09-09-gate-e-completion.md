# Gate E Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining deterministic Gate E release-readiness gaps without regressing the current Intelligence Fabric.

**Architecture:** Forward-port only proven missing Gate E capabilities onto current `main`. Keep current inference routing as the source of truth, add deterministic integration/chaos/performance/release tests, add hardened production container topology, and add independent security and real-provider workflows.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, PostgreSQL 16, Redis 7, pytest, Ruff, mypy, React, Playwright, Docker Compose, GitHub Actions, CodeQL.

**Spec:** Existing Gate E branch `codex/system-gauntlet-gate-e` plus current Intelligence Fabric on `main`.

## Global Constraints

- Do not merge the stale Gate E branch directly.
- Preserve `backend/app/inference` as the canonical inference subsystem.
- Preserve `openai`, `freellmapi`, and `openai_compatible` provider support.
- Never commit secrets; production/provider workflows consume GitHub/environment secrets only.
- Operational runtime must reject `fake`; deterministic tests may use local stubs.
- No prompt/body logging or raw provider exception leakage.
- No production completion claim without fresh CI evidence.

---

### Task 1: Deterministic system gauntlet and chaos recovery

**Files:**
- Create: `backend/tests/test_system_gauntlet.py`
- Create: `backend/tests/test_chaos_recovery.py`

**Interfaces:**
- Consumes: `LivingCoreService`, `AgentRuntime`, `MissionCompletionEngine`, `ModelRouter`.
- Produces: deterministic evidence that authorized missions manifest and recover from one transient provider failure.

- [ ] Add the deterministic full mission-path integration test copied forward against current contracts.
- [ ] Add the transient-provider retry/recovery integration test copied forward against current contracts.
- [ ] Run full backend CI and fix only current-contract incompatibilities.

### Task 2: Projection performance budget

**Files:**
- Create: `backend/tests/test_projection_performance_budget.py`

**Interfaces:**
- Consumes: `system_snapshot(session, persist=False)`.
- Produces: smoke latency budget evidence for 100 universes and 100 agents.

- [ ] Add the 2.0 second smoke budget test.
- [ ] Run the test in CI-backed PostgreSQL.
- [ ] Keep the threshold deterministic and environment-tolerant; do not invent production latency claims.

### Task 3: Hardened production topology and release invariants

**Files:**
- Create: `docker-compose.prod.yml`
- Create: `backend/tests/test_release_invariants.py`

**Interfaces:**
- Consumes: current provider environment contract from `.env.example` and `backend/app/inference/bootstrap.py`.
- Produces: externally exposed frontend only; internal PostgreSQL/Redis; read-only application containers; provider configuration passed through without hardcoded credentials.

- [ ] Add hardened frontend/API/worker/PostgreSQL/Redis production services.
- [ ] Pass all supported current inference provider variables to API/worker.
- [ ] Add static release invariants verifying no state-service host ports, no source bind mounts, production mode, read-only/no-new-privileges, and no fake provider default.
- [ ] Run release invariant tests.

### Task 4: Security workflow

**Files:**
- Create: `.github/workflows/security.yml`

**Interfaces:**
- Consumes: Python and frontend dependency manifests.
- Produces: CodeQL plus dependency audit gates on PRs/main and manual dispatch.

- [ ] Add Python and JavaScript/TypeScript CodeQL analysis.
- [ ] Add `pip-audit` for installed backend dependencies.
- [ ] Add `npm audit --audit-level=high` for frontend dependencies.
- [ ] Keep workflow permissions read-only except permissions required by the actions themselves.

### Task 5: Multi-provider real-provider gauntlet

**Files:**
- Create: `backend/tests/test_real_provider_mission.py`
- Create: `.github/workflows/real-provider-gauntlet.yml`

**Interfaces:**
- Consumes: `build_model_router()` and current provider-specific environment variables.
- Produces: manually triggered evidence that one configured real provider can execute a mission through `AgentRuntime` to `MANIFESTED`.

- [ ] Parameterize the real-provider test from `LLM_PROVIDER` instead of hardcoding OpenAI.
- [ ] Reject `fake` and require provider-specific configuration for `openai`, `freellmapi`, or `openai_compatible`.
- [ ] Keep the workflow manual-only so missing external secrets never break deterministic CI.
- [ ] Verify the workflow definition and deterministic suite; do not claim the live provider gate passed until it is actually run with credentials.

### Task 6: Final verification and integration

**Files:**
- Modify only if verification exposes a real defect.

**Interfaces:**
- Consumes: all tasks above.
- Produces: merge-ready Gate E completion PR.

- [ ] Verify current `main` post-merge CI is green.
- [ ] Run PR CI: Ruff, mypy, Alembic, pytest, frontend build/unit/Playwright.
- [ ] Inspect Security workflow result.
- [ ] Merge only after deterministic required checks are green.
- [ ] Verify push-to-main CI after merge.
