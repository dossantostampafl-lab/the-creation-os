# FreeLLMAPI Intelligence Fabric Integration — Design

**Date:** 2026-09-09
**Revision:** 2 — aligned to the verified `app.inference` runtime

## Goal

Integrate FreeLLMAPI into THE CREATION OS as an optional provider-aggregation gateway behind Creation-owned inference policy, without allowing provider credentials, routing policy, governance decisions, or fake telemetry to leak into cognitive or execution layers.

## Verified Starting Point

The operational inference path already exists and must be extended rather than duplicated:

- `app.inference.contracts` defines `ModelRequirements`, `InferenceRequest`, `InferenceResponse`, `ProviderHealth`, `InferenceError`, and `ProviderUnavailable`.
- `app.inference.provider.InferenceProvider` defines `generate`, `stream`, and `health`.
- `app.inference.registry.ProviderRegistry` owns registered providers.
- `app.inference.router.ModelRouter` applies explicit preferred/fallback provider selection and health checks.
- `app.inference.bootstrap.build_model_router()` currently registers OpenAI when `LLM_PROVIDER=openai` and explicitly rejects fake as an operational provider.
- `app.inference.openai_provider.OpenAIResponsesProvider` is the current concrete provider implementation.
- `app.worker.run_worker()` constructs `build_model_router()` and injects it into `AgentRuntime`; therefore `app.inference` is the live operational boundary.
- `app.ai` is a legacy/minimal compatibility surface and is not the correct place to create a second production router.

The canonical upstream evaluated for this integration is `tashfeenahmed/freellmapi`. Its public documentation describes an OpenAI-compatible self-hosted gateway with `/v1/chat/completions`, `/v1/responses`, `/v1/embeddings`, streaming, tools/structured outputs, routing, rate tracking, failover, encrypted provider keys, and a unified bearer token. These are upstream claims/capabilities; Creation must not assume every routed model supports every capability.

## Architectural Decision

FreeLLMAPI becomes another `InferenceProvider` inside the existing Creation inference subsystem.

```text
Creator / cognitive layers
        -> mission + capability governance
        -> AgentRuntime
        -> ModelRouter
             -> ProviderRegistry
                  -> OpenAIResponsesProvider
                  -> FreeLLMAPIProvider
                  -> future direct/local providers
                       -> FreeLLMAPI /v1
                            -> upstream provider/model pool
```

Creation owns which provider may be selected and which fallbacks are allowed. FreeLLMAPI may perform low-level upstream aggregation/failover internally, but it does not become Creation's policy authority.

## Phase 1 Scope

1. Extend existing inference error semantics with normalized failure classes while preserving `ProviderUnavailable` compatibility.
2. Add `FreeLLMAPIProvider` implementing the existing `InferenceProvider` protocol.
3. Use the OpenAI-compatible `/v1/chat/completions` surface for generation and streaming.
4. Add `LLM_PROVIDER=freellmapi` support in `build_model_router()`.
5. Add secret-backed configuration:
   - `FREELLMAPI_BASE_URL`
   - `FREELLMAPI_API_KEY`
   - `FREELLMAPI_MODEL`
   - `FREELLMAPI_TIMEOUT_SECONDS`
6. Add a cheap health probe using `/v1/models`.
7. Preserve explicit fallback behavior in `ModelRouter`; no provider is silently inserted into a fallback chain.
8. Add FreeLLMAPI embeddings through the existing `app.ai.embeddings` compatibility layer only when `EMBEDDING_PROVIDER=freellmapi`.
9. Keep prompts, authorization headers, API keys, and upstream credentials out of exception strings and operational logs.
10. Do not vendor or copy FreeLLMAPI source code.

## Contracts

### Existing request/response remain canonical

Phase 1 does not introduce parallel `LLMRequest`/`LLMResult` types. The canonical runtime types remain:

```python
InferenceRequest
InferenceResponse
ModelRequirements
ProviderHealth
InferenceProvider
```

This prevents a duplicate abstraction layer.

### Error normalization

The existing `InferenceError` hierarchy will be extended with specific subclasses while retaining `ProviderUnavailable` as the general routing-compatible failure:

- `InferenceConfigurationError`
- `InferenceAuthenticationError`
- `InferenceRateLimitError`
- `InferenceTimeoutError`
- `InferenceUpstreamResponseError`
- `ProviderUnavailable`

Router fallback remains conservative: Phase 1 preserves current behavior and falls back only when the router receives a `ProviderUnavailable`-compatible error from an explicitly allowed provider. Specific operational errors may subclass `ProviderUnavailable` when fallback is safe; configuration/authentication errors should fail closed and must not silently route around a misconfiguration unless explicitly designed later.

## FreeLLMAPI Provider

`FreeLLMAPIProvider` implements:

```python
name = "freellmapi"

async def generate(request: InferenceRequest) -> InferenceResponse
async def stream(request: InferenceRequest) -> AsyncIterator[str]
async def health() -> ProviderHealth
```

Generation maps:

```text
InferenceRequest.messages -> messages
request.model or configured default -> model
requirements.max_output_tokens -> max_tokens
metadata-approved optional parameters -> explicitly allowlisted fields only
```

The response is normalized from OpenAI Chat Completions shape:

```text
choices[0].message.content -> InferenceResponse.content
choices[0].finish_reason -> finish_reason
usage -> integer-only usage mapping
model -> resolved model
provider -> "freellmapi"
```

Malformed JSON or missing `choices/message/content` is rejected; it must not produce a false successful response.

## Streaming

Streaming uses `/v1/chat/completions` with `stream=true` and parses SSE `data:` frames. Only textual `choices[].delta.content` is yielded in Phase 1. Tool calls are not executed by this adapter. A later phase may normalize tool-call deltas into Creation capability intents after schema validation and governance review.

## Configuration and Secrets

`FREELLMAPI_API_KEY` is a `SecretStr`. No secret may be included in exception text, logs, metrics labels, Chronicle payloads, frontend state, or test snapshots.

`FREELLMAPI_BASE_URL` must be explicit when `LLM_PROVIDER=freellmapi`; no production default points to a public host. The URL must use `http` or `https`.

Upstream Google/Groq/Cerebras/NVIDIA/OpenRouter/etc. keys remain in the separately deployed FreeLLMAPI service. Creation receives only the unified FreeLLMAPI bearer token.

## Health

`health()` performs a bounded `GET /v1/models` call and returns existing `ProviderHealth(provider="freellmapi", available=...)` without invoking inference. Failure detail is normalized to status/class only and never contains secrets or response bodies.

## Embeddings Compatibility

`app.ai.embeddings.build_embedding_model()` may resolve `EMBEDDING_PROVIDER=freellmapi` and call `/v1/embeddings` using the same FreeLLMAPI base URL/key. Existing direct OpenAI and deterministic test embedding paths remain unchanged.

This does not make `app.ai` a second inference router; it is only the existing embedding compatibility surface.

## Security Boundaries

- Treat FreeLLMAPI as an external network dependency even when self-hosted.
- Validate base URL scheme.
- Redact authorization values and never log request bodies by default.
- Do not forward arbitrary `InferenceRequest.metadata` into upstream JSON; use an explicit allowlist.
- Do not execute tool calls returned by FreeLLMAPI in Phase 1.
- Do not use FreeLLMAPI to bypass provider safety/policy restrictions.
- An upstream outage must degrade inference only; it must not break authentication, memory, governance, or Chronicle storage.
- Fake providers remain forbidden in the operational runtime.

## Testing Strategy

TDD is mandatory. Tests use `httpx.MockTransport` or an injectable transport/client factory so no live key is required.

Required tests:

- provider request serialization and bearer auth
- response normalization
- streaming delta normalization
- `/v1/models` health behavior
- 401/403 normalization
- 429 normalization
- timeout/network failure normalization
- 5xx normalization
- invalid JSON and malformed success payload rejection
- secret redaction in exception strings
- bootstrap registration for `LLM_PROVIDER=freellmapi`
- missing URL/key/model fail closed
- explicit router fallback behavior remains unchanged
- FreeLLMAPI embeddings request/response behavior
- existing OpenAI inference tests remain green

## Rollout

Phase 1: concrete FreeLLMAPI provider + bootstrap/config + embeddings compatibility + tests.

Phase 2: enrich existing `ModelRequirements`, registry metadata, and router scoring with capability/model evidence rather than creating a second registry.

Phase 3: budget, circuit-breaker, rate-limit-aware routing, and reason-aware fallback.

Phase 4: verified provider/model health and telemetry in the dashboard.

Phase 5: benchmark-driven routing and additional direct/local providers.

## Acceptance Criteria for Phase 1

- `LLM_PROVIDER=freellmapi` registers a real `FreeLLMAPIProvider` in the existing `ModelRouter` path used by `worker.py`.
- No parallel production router is added under `app.ai`.
- Generate, stream, and health conform to `InferenceProvider`.
- Missing configuration fails explicitly.
- Critical upstream failures are normalized and secret-safe.
- Explicit router fallback semantics are preserved.
- Embeddings can use FreeLLMAPI when explicitly configured.
- Production never falls back to fake.
- Ruff, mypy, migrations, pytest, frontend build/tests/E2E are verified through CI before readiness is claimed.

## Non-Goals

- Copying FreeLLMAPI internals.
- Trusting advertised model capability without Creation-side evidence.
- Implementing every upstream provider directly in Creation.
- Multi-tenant billing.
- Autonomous governance changes.
- Exposing secrets to the dashboard.
- Claiming free-tier quotas as guaranteed capacity or SLA.
