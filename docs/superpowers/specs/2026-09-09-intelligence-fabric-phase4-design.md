# Intelligence Fabric Phase 4 — Verified Health and Dashboard Telemetry

**Status:** Approved as part of the previously accepted Intelligence Fabric rollout.

## Goal

Expose verified, secret-safe provider/model health to the authenticated Creation dashboard without inventing telemetry or coupling the UI to provider SDKs.

## Architectural Decision

Creation will expose a protected `/api/v1/system/inference` endpoint. The endpoint builds the same canonical `ModelRouter` configuration used by the worker, calls provider `health()` methods directly, and returns a normalized snapshot containing only Creation-owned provider/model evidence and bounded health state.

No inference request is executed by the telemetry endpoint. No prompt, API key, authorization header, upstream body, or FreeLLMAPI internal credential can enter the response.

If the operational inference provider is intentionally disabled/unconfigured (for example test `fake`), the endpoint returns a deterministic `configured=false` snapshot instead of fabricating provider health or throwing a 500.

## Snapshot Contract

```text
InferenceStatusSnapshot
- configured: bool
- configured_provider: string
- providers: list[ProviderStatus]

ProviderStatus
- provider: string
- available: bool
- detail: str | None
- models: list[ModelStatus]

ModelStatus
- model: string
- is_default: bool
- capabilities: sorted list[str]
- cost_tier: UNKNOWN | FREE | LOW | PREMIUM | FRONTIER
```

Health `detail` is whatever normalized secret-safe `ProviderHealth` already permits. Raw exception messages from bootstrap/configuration are not exposed.

## API Boundary

`app.api.inference_status` owns HTTP/auth wiring only. `app.inference.status` owns snapshot construction and is testable without FastAPI.

The route uses the existing authenticated `actor` dependency so inference topology is not exposed publicly.

## Dashboard Integration

The React dashboard fetches `/system/inference` during hydration and after Chronicle refreshes. A compact `INFERENCE FABRIC` panel shows configured provider, health, default model, capability evidence, and cost tier.

The panel must represent unavailable/unconfigured states explicitly. It may not generate placeholder providers, fake latency, fake token counts, or synthetic uptime.

## Security Invariants

- No secrets in API response, logs, frontend state, fixtures, or tests.
- No prompts or request bodies in telemetry.
- No provider discovery outside the canonical registry.
- No model capability inferred from provider marketing or model names.
- No health call executes inference.
- Dashboard remains read-only for provider configuration.

## Testing

Backend TDD covers configured provider snapshot, unconfigured/fake state, unavailable provider health, model evidence normalization, and authenticated route behavior. Frontend tests cover API parsing and visible rendering of verified/unconfigured states. Full Ruff, mypy, Alembic, pytest, frontend build/unit, and Playwright gates remain mandatory.
