# FreeLLMAPI Intelligence Fabric Integration — Design

**Date:** 2026-09-09

## Goal

Integrate FreeLLMAPI into THE CREATION OS as an optional provider-aggregation gateway behind a Creation-owned Adaptive Multi-LLM Intelligence Fabric, without allowing provider-specific behavior, credentials, routing policy, governance decisions, or fake telemetry to leak into cognitive layers such as DEUS, SOPHIA, ROCKMAM, Inceptions, Universes, or agents.

## Verified Starting Point

The current backend AI surface is deliberately small. `app.ai.interfaces.LanguageModel` exposes `generate(prompt, max_tokens)` and `EmbeddingModel` exposes `embed(text)`. `app.ai.fake.FakeLanguageModel` is prohibited in production. `app.ai.embeddings` already resolves embedding providers at invocation time and uses `httpx` for OpenAI embeddings. `app.config.Settings` already has `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `EMBEDDING_PROVIDER`, and `EMBEDDING_MODEL` settings.

The canonical FreeLLMAPI repository evaluated for this design is `tashfeenahmed/freellmapi`. Its current public documentation describes a self-hosted OpenAI-compatible gateway, multiple upstream providers, `/v1/chat/completions`, `/v1/responses`, `/v1/embeddings`, streaming, tools/structured outputs, routing, rate tracking, failover, encrypted provider keys, and a unified bearer token. Those are upstream capabilities; THE CREATION OS must not assume every upstream model supports every capability.

## Architectural Decision

FreeLLMAPI is a gateway adapter, not the intelligence policy authority.

```text
Creator
  -> DEUS / SOPHIA / ROCKMAM / Inception / Agents
  -> Creation Intelligence Fabric
       -> capability policy
       -> mission policy
       -> provider/model registry
       -> routing and fallback policy
       -> budget policy
       -> telemetry/audit
       -> FreeLLMAPI adapter
            -> FreeLLMAPI /v1
                 -> upstream providers/models
       -> future direct adapters (premium/local escape hatches)
```

The Creation layer owns *why* a model/provider may be selected. FreeLLMAPI may perform low-level provider aggregation and upstream failover, but Creation retains final admission, capability, budget, privacy, and mission policy.

## Scope of the First Integration

The first implementation slice is intentionally narrow and testable:

1. Add provider-agnostic request/result types for chat generation while preserving backward compatibility with the existing `LanguageModel.generate()` protocol.
2. Add a FreeLLMAPI HTTP adapter using the documented OpenAI-compatible `/v1/chat/completions` surface.
3. Add an embedding adapter for `/v1/embeddings` so chat and embeddings can use the same gateway when configured.
4. Add runtime configuration using secrets only:
   - `FREELLMAPI_BASE_URL`
   - `FREELLMAPI_API_KEY`
   - `FREELLMAPI_MODEL`
   - `FREELLMAPI_TIMEOUT_SECONDS`
5. Add provider resolution so `LLM_PROVIDER=freellmapi` selects the adapter; missing credentials/configuration must fail closed with a specific configuration error, not silently fall back to fake.
6. Add a health probe that verifies the gateway is reachable without exposing credentials.
7. Add normalized exceptions for configuration, authentication, rate limit, timeout, unavailable provider, malformed upstream response, and unsupported capability.
8. Add request metadata needed for later routing: mission/agent identifiers, requested capabilities, timeout class, and optional model preference. These fields must be optional for backward compatibility.
9. Add telemetry hooks that record provider/model/status/latency/fallback reason while explicitly redacting prompts, credentials, authorization headers, and provider keys by default.
10. Keep `FakeLanguageModel` and deterministic fake embeddings strictly as test/development doubles; no production routing path may silently select them.

This slice does **not** import FreeLLMAPI source code into THE CREATION OS, does not copy its encrypted-key database, does not expose its admin dashboard, and does not hand Creation governance decisions to the external gateway.

## Interfaces

### Backward-compatible protocol

Existing callers may continue to use:

```python
await language_model.generate(prompt, max_tokens=...)
```

A richer provider-agnostic interface will be added alongside it:

```python
@dataclass(frozen=True)
class LLMRequest:
    messages: tuple[LLMMessage, ...]
    model: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    capabilities: frozenset[LLMCapability] = frozenset()
    mission_id: str | None = None
    agent_id: str | None = None

@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str
    model: str
    finish_reason: str | None
    usage: LLMUsage | None
```

The initial FreeLLMAPI adapter must implement both the rich interface and the legacy `generate()` bridge.

### Capabilities

Initial enum values:

- `TEXT`
- `STREAMING`
- `TOOLS`
- `STRUCTURED_OUTPUT`
- `VISION`
- `EMBEDDINGS`

The adapter must never claim support merely because FreeLLMAPI can route the request. Capability support is determined by Creation registry/policy metadata and later benchmark evidence.

## Configuration and Secrets

`FREELLMAPI_API_KEY` is a `SecretStr`. It must never be returned from API endpoints, included in logs, metrics labels, exception messages, Chronicle payloads, frontend responses, or test snapshots.

`FREELLMAPI_BASE_URL` defaults only in development/test to `http://freellmapi:3000` when explicitly enabled by deployment configuration. Production should require an explicit URL to avoid accidentally routing sensitive prompts to an unintended host.

No provider key from Google, Groq, Cerebras, NVIDIA, OpenRouter, or other upstreams belongs in THE CREATION OS once FreeLLMAPI is used as the aggregator. Those remain inside the separately deployed FreeLLMAPI service or its secret store.

## Request Flow

1. A cognitive component asks the Creation Intelligence Fabric for inference.
2. Creation policy validates mission, capabilities, privacy class, model preference, and budget tier.
3. Provider resolution selects `freellmapi` only if it is configured and permitted.
4. The adapter sends an OpenAI-compatible request to the configured FreeLLMAPI endpoint.
5. HTTP status and response structure are normalized into Creation exceptions/results.
6. Telemetry records metadata only: provider, resolved model, status, latency, token counts if present, and normalized failure class.
7. No prompt/body logging occurs by default.

## Error Semantics

- Missing gateway URL/key/model -> `LLMConfigurationError`
- 401/403 -> `LLMAuthenticationError`
- 429 -> `LLMRateLimitError`
- connect/read timeout -> `LLMTimeoutError`
- 5xx/network unavailable -> `LLMProviderUnavailableError`
- malformed or incompatible JSON -> `LLMUpstreamResponseError`
- requested unsupported capability -> `LLMUnsupportedCapabilityError`

No error path may automatically switch to `fake` in production.

## Health

A FreeLLMAPI health checker should prefer a cheap non-generative endpoint such as `/v1/models` or an upstream documented health endpoint. Health state is normalized to `HEALTHY`, `DEGRADED`, `RATE_LIMITED`, `UNAVAILABLE`, or `DISABLED_NO_CREDENTIAL`. Health checks must use bounded timeouts and must not generate billable/free-tier inference merely to determine liveness unless no metadata endpoint is available.

## Security Boundaries

- FreeLLMAPI is treated as an external network dependency even when self-hosted.
- Base URL must be validated to `http`/`https`; production deployment policy should restrict it to approved hosts/network paths.
- Authorization header values are always redacted.
- Prompt and tool payloads are not logged by default.
- Provider credentials never enter frontend state.
- A FreeLLMAPI outage must degrade inference, not core authentication, governance, memory, or Chronicle availability.
- A malformed FreeLLMAPI response must not be executed as a tool call without schema validation.
- Creation must not use FreeLLMAPI behavior to bypass upstream provider safety/policy restrictions.

## Testing Strategy

TDD is mandatory for production behavior.

Unit tests will cover configuration validation, request translation, response parsing, secret redaction, status-to-exception mapping, capability rejection, and legacy `generate()` compatibility.

HTTP integration tests will use `httpx.MockTransport` (or equivalent transport-level fake) to assert real serialized requests and normalized responses without external network dependence.

Failure tests will cover 401/403, 429, timeout, 5xx, invalid JSON, missing choices/content, and unreachable gateway.

Production-safety tests will prove `fake` cannot be selected as an implicit fallback and secrets do not appear in exception strings or telemetry payloads.

A later deployment/E2E gate may test a real self-hosted FreeLLMAPI instance, but no repository test may require live third-party API keys.

## Rollout

Phase 1 is adapter + normalized contracts + configuration + tests. Phase 2 adds provider/model/capability registries and Creation-owned routing. Phase 3 adds mission-aware scoring, budget policy, circuit breakers, and fallback. Phase 4 exposes live provider/model health and verified telemetry in the dashboard. Phase 5 adds benchmark-driven routing and optional direct premium/local adapters.

Each phase must remain independently deployable and must not introduce fake operational data.

## Acceptance Criteria for Phase 1

- `LLM_PROVIDER=freellmapi` resolves a real FreeLLMAPI adapter.
- Existing `LanguageModel.generate()` callers remain compatible.
- Chat completion and embedding requests are translated through configurable `/v1` endpoints.
- Missing configuration fails explicitly.
- Authentication, rate limit, timeout, upstream 5xx, and malformed-response failures are normalized.
- Secrets and prompts are absent from default logs/telemetry.
- Production never falls back to fake.
- Tests cover success and critical failure paths.
- Existing backend tests remain green.
- Ruff/mypy status is checked and any pre-existing failures are distinguished from regressions introduced by this work.

## Explicit Non-Goals for Phase 1

- Copying FreeLLMAPI internals into this repository.
- Trusting FreeLLMAPI advertised model capability without Creation-side metadata/evidence.
- Implementing all 34 upstream providers directly in Creation.
- Multi-tenant billing.
- Autonomous policy rewriting.
- Sending secrets to the dashboard.
- Claiming free-tier capacity or model availability as guaranteed SLA.
