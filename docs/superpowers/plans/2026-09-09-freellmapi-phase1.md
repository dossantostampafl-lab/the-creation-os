# FreeLLMAPI Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add FreeLLMAPI as a production-safe `InferenceProvider` in THE CREATION OS existing operational inference runtime.

**Architecture:** Extend `app.inference`; do not create a parallel production router under `app.ai`. `ModelRouter` and `ProviderRegistry` remain Creation-owned. FreeLLMAPI is one explicit provider adapter using OpenAI-compatible chat/streaming plus a health probe. `app.ai.embeddings` is extended only for the existing embedding compatibility path.

**Tech Stack:** Python 3.12, Pydantic, `httpx`, pytest/pytest-asyncio, Ruff, mypy, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-09-freellmapi-intelligence-fabric-design.md`

## Global Constraints

- Preserve existing `InferenceRequest`, `InferenceResponse`, `ModelRequirements`, `ProviderHealth`, `InferenceProvider`, `ProviderRegistry`, and `ModelRouter` as canonical runtime abstractions.
- Never silently fall back to fake in the operational runtime.
- Fallback remains explicit through `ModelRequirements.fallback_providers`.
- `FREELLMAPI_API_KEY` is wrapped in `SecretStr` before entering provider construction and must never appear in errors, logs, telemetry, or frontend state.
- No live third-party key is required by tests.
- Do not vendor FreeLLMAPI source code.
- Do not execute tool calls returned by FreeLLMAPI in Phase 1.
- Do not forward arbitrary request metadata upstream.
- Production behavior follows RED -> GREEN -> REFACTOR.

---

### Task 1: FreeLLMAPI provider behavior

**Files:**
- Modify: `backend/app/inference/contracts.py`
- Create: `backend/app/inference/freellmapi_provider.py`
- Test: `backend/tests/test_freellmapi_provider.py`

**Interfaces:**
- Produces `FreeLLMAPIProvider(api_key, default_model, base_url, timeout_seconds=60.0, transport=None)`.
- Implements `generate(InferenceRequest) -> InferenceResponse`, `stream(InferenceRequest) -> AsyncIterator[str]`, and `health() -> ProviderHealth`.
- Extends the existing error hierarchy with configuration/authentication/rate-limit/timeout/upstream-response errors without breaking router compatibility.

- [x] Write tests first for request serialization, bearer auth, response parsing, health, status mapping, malformed payloads, timeout/network failure, streaming deltas, and secret-safe errors.
- [x] Verify CI reaches pytest and fails because `FreeLLMAPIProvider` / new errors do not exist.
- [x] Implement minimal provider and error classes.
- [x] Verify provider tests and existing inference tests pass.

### Task 2: Runtime configuration and bootstrap

**Files:**
- Create: `backend/app/inference/freellmapi_config.py`
- Modify: `backend/app/inference/bootstrap.py`
- Test: `backend/tests/test_freellmapi_bootstrap.py`

**Interfaces:**
- Dedicated environment configuration: `FREELLMAPI_BASE_URL`, `FREELLMAPI_API_KEY`, `FREELLMAPI_MODEL`, `FREELLMAPI_TIMEOUT_SECONDS`.
- `FREELLMAPI_API_KEY` is converted to `SecretStr` by the dedicated loader.
- `LLM_PROVIDER=freellmapi` registers `FreeLLMAPIProvider` in the existing `ProviderRegistry` returned through `ModelRouter`.
- FreeLLMAPI chat does not reuse `LLM_API_KEY` or `LLM_MODEL`; direct OpenAI configuration remains independent.

- [x] Write failing tests for successful registration and missing URL/key/model fail-closed behavior.
- [x] Verify RED in CI.
- [x] Implement dedicated environment loader + bootstrap registration; preserve direct OpenAI and fake rejection behavior.
- [x] Verify GREEN in CI.

### Task 3: FreeLLMAPI embeddings compatibility

**Files:**
- Modify: `backend/app/ai/embeddings.py`
- Test: `backend/tests/test_freellmapi_embeddings.py`

**Interfaces:**
- `EMBEDDING_PROVIDER=freellmapi` calls `${FREELLMAPI_BASE_URL}/embeddings` with the shared dedicated `FREELLMAPI_API_KEY` and `EMBEDDING_MODEL`.
- Existing deterministic test and direct OpenAI embedding paths remain intact.

- [x] Write failing tests for serialized request, parsed vector, missing configuration, malformed response, and secret-safe failure.
- [x] Verify RED in CI.
- [x] Implement minimal embedding adapter/factory branch.
- [x] Verify GREEN in CI.

### Task 4: Deployment placeholders and safety documentation

**Files:**
- Modify: `.env.example`
- Modify: `backend/.env.example`

- [x] Add placeholder-only `FREELLMAPI_API_KEY`, `FREELLMAPI_MODEL`, `FREELLMAPI_BASE_URL`, and `FREELLMAPI_TIMEOUT_SECONDS`; no real credentials.
- [x] Inspect PR diff for accidental credentials, prompt/body logging, authorization leakage, and arbitrary metadata passthrough.

### Task 5: Full verification gate

- [x] Verify backend CI: `ruff check .`, `mypy app`, migrations, full `pytest`.
- [x] Verify frontend build/tests/Playwright remain green.
- [x] Inspect PR diff for accidental secrets, prompt/body logging, arbitrary metadata passthrough, duplicate inference abstractions, and unrelated refactors.
- [x] Reconcile implementation with each Phase 1 acceptance criterion in the revised design.
- [ ] Obtain a fresh green CI after this documentation reconciliation.
- [ ] Mark PR ready only after that fresh green CI. Do not merge automatically without an explicit merge decision.
