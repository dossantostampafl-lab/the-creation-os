# Intelligence Fabric Phase 5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the Intelligence Fabric with opt-in evidence-ranked routing and a generic fail-closed OpenAI-compatible provider.

**Architecture:** Extend the existing contracts/registry/router without changing default ordered routing. Add a focused provider adapter/config module following the established FreeLLMAPI/OpenAI provider patterns, then bootstrap it through the canonical router.

**Tech Stack:** Python 3.12, Pydantic, httpx, pytest, Ruff, mypy, FastAPI, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-09-intelligence-fabric-phase5-design.md`

## Global Constraints

- Default provider ordering remains unchanged.
- Benchmark selection is opt-in and can only reorder explicitly authorized candidates.
- Missing evidence must never be converted into fabricated metrics.
- Existing capability, budget, health, cooldown and circuit gates remain authoritative.
- Generic OpenAI-compatible configuration fails closed.
- Secrets, prompts and upstream response bodies never enter normalized errors or telemetry.

---

### Task 1: Benchmark evidence contract and registry

**Files:**
- Modify: `backend/app/inference/contracts.py`
- Modify: `backend/app/inference/registry.py`
- Create: `backend/tests/test_inference_benchmark_registry.py`

**Interfaces:**
- `ProviderBenchmarkEvidence(provider, model, suite_id, score, sample_count, observed_at)`
- `ProviderRegistry.register_benchmark_evidence(evidence)`
- `ProviderRegistry.get_benchmark_evidence(provider, model)`

- [ ] Write RED tests proving evidence immutability, validation, duplicate-suite rejection and deterministic latest evidence lookup.
- [ ] Run focused pytest and confirm semantic RED.
- [ ] Implement minimal contract/registry storage.
- [ ] Run focused pytest and confirm GREEN.

### Task 2: Opt-in benchmark routing

**Files:**
- Modify: `backend/app/inference/contracts.py`
- Modify: `backend/app/inference/router.py`
- Create: `backend/tests/test_inference_benchmark_routing.py`

**Interfaces:**
- `ModelRequirements.routing_strategy: Literal["ordered", "benchmark"] = "ordered"`
- Benchmark mode reorders only the existing authorized candidate list by matching evidence score descending; ties/missing evidence preserve original order.

- [ ] Write RED tests for default ordered behavior, benchmark reordering, no implicit discovery, tie stability and missing-evidence stability.
- [ ] Run focused pytest and confirm semantic RED.
- [ ] Implement minimal candidate ordering helper.
- [ ] Run focused pytest and confirm GREEN.

### Task 3: Generic OpenAI-compatible provider

**Files:**
- Create: `backend/app/inference/openai_compatible_provider.py`
- Create: `backend/tests/test_openai_compatible_provider.py`

**Interfaces:**
- `OpenAICompatibleProvider(name, base_url, default_model, api_key=None, timeout_seconds=60.0, transport=None)`
- `generate`, `stream`, `health` implement existing provider contract.

- [ ] Write RED tests for generate, stream, health, optional auth, timeout, 401/403, 429, malformed and 5xx normalization, and invalid constructor inputs.
- [ ] Run focused pytest and confirm semantic RED.
- [ ] Implement minimal provider with secret-safe errors.
- [ ] Run focused pytest and confirm GREEN.

### Task 4: Fail-closed configuration and bootstrap

**Files:**
- Create: `backend/app/inference/openai_compatible_config.py`
- Modify: `backend/app/inference/bootstrap.py`
- Modify: `.env.example`
- Create: `backend/tests/test_openai_compatible_bootstrap.py`

**Interfaces:**
- Environment: `OPENAI_COMPATIBLE_BASE_URL`, `OPENAI_COMPATIBLE_MODEL`, `OPENAI_COMPATIBLE_API_KEY`, `OPENAI_COMPATIBLE_TIMEOUT_SECONDS`.
- `LLM_PROVIDER=openai_compatible` registers only the configured generic provider/model profile.

- [ ] Write RED tests for valid bootstrap and missing/invalid URL/model/timeout fail-closed behavior.
- [ ] Run focused pytest and confirm semantic RED.
- [ ] Implement config loader/bootstrap branch and placeholder-only env documentation.
- [ ] Run focused pytest and confirm GREEN.

### Task 5: Full verification and cumulative integration

**Files:**
- Audit all Phase 5 changes and stacked Phase 1–4 PRs.

- [ ] Run full GitHub Actions backend gate: Ruff, mypy, Alembic, pytest.
- [ ] Run full frontend gate: build, unit and Playwright E2E.
- [ ] Audit Phase 5 PR diff for secret leakage, implicit provider discovery and fabricated benchmark telemetry.
- [ ] Mark Phase 3/4/5 PRs ready only when their latest CI is green.
- [ ] Integrate the stack sequentially into `main`, preserving green gates.
- [ ] Run a fresh cumulative CI on `main`/final integration head before claiming completion.
