# FreeLLMAPI Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-safe, provider-agnostic FreeLLMAPI gateway adapter to THE CREATION OS while preserving the existing `LanguageModel.generate()` and embedding call sites.

**Architecture:** THE CREATION OS owns policy and provider selection. FreeLLMAPI is an optional HTTP gateway behind a narrow adapter. The adapter translates Creation request types to OpenAI-compatible `/v1/chat/completions` and `/v1/embeddings`, normalizes failures, exposes a non-generative health probe, and never leaks secrets or prompt bodies into errors/telemetry.

**Tech Stack:** Python 3.12, FastAPI backend, Pydantic v1 settings compatibility, `httpx`, `pytest`, `pytest-asyncio`, Ruff, mypy, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-09-freellmapi-intelligence-fabric-design.md`

## Global Constraints

- Keep `LanguageModel.generate(prompt, max_tokens)` backward compatible.
- Never silently fall back to fake in production.
- `FREELLMAPI_API_KEY` must be represented as `SecretStr` and never appear in exception text, logs, telemetry, or frontend responses.
- No live third-party key is required by tests.
- FreeLLMAPI is an external gateway, not the Creation governance authority.
- Phase 1 must not import or vendor FreeLLMAPI source code.
- All production behavior follows RED -> GREEN -> REFACTOR.

---

### Task 1: Provider-agnostic contracts and errors

**Files:**
- Create: `backend/app/ai/types.py`
- Create: `backend/app/ai/errors.py`
- Modify: `backend/app/ai/interfaces.py`
- Test: `backend/tests/test_freellmapi_contracts.py`

**Interfaces:**
- Produces `LLMRole`, `LLMCapability`, `LLMMessage`, `LLMUsage`, `LLMRequest`, `LLMResult`, `HealthState`, `ProviderHealth`.
- Produces normalized exception hierarchy rooted at `LLMError`.
- Adds a rich async execution protocol without removing the legacy `LanguageModel` protocol.

- [ ] **Step 1: Write failing contract tests** proving immutable request/result types, enum values, legacy protocol presence, and exception hierarchy.
- [ ] **Step 2: Trigger CI and verify the new tests fail because the production types/modules do not exist.**
- [ ] **Step 3: Implement minimal types/errors/interfaces needed to satisfy the tests.**
- [ ] **Step 4: Trigger CI and verify contract tests plus existing backend tests pass.**

### Task 2: FreeLLMAPI chat adapter

**Files:**
- Create: `backend/app/ai/providers/__init__.py`
- Create: `backend/app/ai/providers/freellmapi.py`
- Test: `backend/tests/test_freellmapi_provider.py`

**Interfaces:**
- Produces `FreeLLMAPIProvider(api_key, base_url, model, timeout_seconds, transport=None)`.
- Produces `execute(request: LLMRequest) -> LLMResult` and legacy `generate(prompt, max_tokens=None) -> str`.
- Produces `health() -> ProviderHealth`.

- [ ] **Step 1: Write failing transport-level tests using `httpx.MockTransport` for serialized chat requests, bearer auth, result parsing, and legacy `generate()`.**
- [ ] **Step 2: Add failing tests for 401/403, 429, timeout, 5xx, invalid JSON, missing choices/content, and secret redaction.**
- [ ] **Step 3: Verify RED in CI.**
- [ ] **Step 4: Implement the minimal HTTP adapter and normalized status/error mapping.**
- [ ] **Step 5: Verify GREEN in CI, then refactor without changing behavior.**

### Task 3: Runtime configuration and provider factory

**Files:**
- Modify: `backend/app/config.py`
- Create: `backend/app/ai/factory.py`
- Test: `backend/tests/test_freellmapi_factory.py`

**Interfaces:**
- Settings: `freellmapi_base_url`, `freellmapi_api_key`, `freellmapi_model`, `freellmapi_timeout_seconds`.
- Produces `build_language_model() -> LanguageModel`.

- [ ] **Step 1: Write failing tests for `LLM_PROVIDER=freellmapi`, explicit missing-key/model failures, fake prohibition in production, and unsupported providers.**
- [ ] **Step 2: Verify RED in CI.**
- [ ] **Step 3: Implement settings and factory with fail-closed semantics.**
- [ ] **Step 4: Verify GREEN in CI and check no existing caller was broken.**

### Task 4: FreeLLMAPI embeddings

**Files:**
- Modify: `backend/app/ai/embeddings.py`
- Test: `backend/tests/test_freellmapi_embeddings.py`

**Interfaces:**
- `EMBEDDING_PROVIDER=freellmapi` uses `/v1/embeddings` through the configured gateway.
- Existing fake deterministic embedding and direct OpenAI embedding behavior remain intact.

- [ ] **Step 1: Write failing tests for request serialization, response parsing, missing configuration, malformed embeddings, and secret redaction.**
- [ ] **Step 2: Verify RED in CI.**
- [ ] **Step 3: Implement the FreeLLMAPI embedding adapter with shared normalized errors where appropriate.**
- [ ] **Step 4: Verify GREEN in CI.**

### Task 5: Health and production-safety regression coverage

**Files:**
- Extend: `backend/tests/test_freellmapi_provider.py`
- Extend: `backend/tests/test_freellmapi_factory.py`

**Interfaces:**
- `health()` probes `/v1/models` with bounded timeout and maps to `HEALTHY`, `RATE_LIMITED`, `UNAVAILABLE`, or `DISABLED_NO_CREDENTIAL` without inference.

- [ ] **Step 1: Add failing health-state tests and tests asserting prompt/API key absence from exception strings.**
- [ ] **Step 2: Verify RED in CI.**
- [ ] **Step 3: Implement minimal health behavior and redaction.**
- [ ] **Step 4: Verify GREEN in CI.**

### Task 6: Full verification and PR gate

**Files:**
- No production file changes unless verification exposes a regression.

- [ ] **Step 1: Run/observe GitHub Actions backend gate: `ruff check .`, `mypy app`, `python -m alembic upgrade head`, `pytest`.**
- [ ] **Step 2: Observe frontend gate to prove backend integration did not break repository-wide CI.**
- [ ] **Step 3: Inspect PR diff for accidental secrets, prompt logging, provider leakage, or unrelated refactors.**
- [ ] **Step 4: Reconcile every acceptance criterion in the design spec against code/tests.**
- [ ] **Step 5: Only after fresh green CI, mark the PR ready for review; do not merge automatically without an explicit merge decision.**
