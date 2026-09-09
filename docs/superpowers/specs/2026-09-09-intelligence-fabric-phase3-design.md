# Intelligence Fabric Phase 3 — Resilience and Budget Design

**Status:** Approved 2026-09-09

## Goal

Extend the Creation-owned inference runtime with budget admission, provider circuit breaking, rate-limit cooldown, and cause-aware fallback while preserving explicit provider governance and fail-closed safety.

## Architecture

`ModelRouter` remains the orchestration authority. Small Creation-owned policy/health components surround it rather than moving governance into provider adapters or an external gateway.

The routing sequence is:

1. Build candidates only from `preferred_provider` plus explicit `fallback_providers`.
2. Apply Phase 2 capability evidence admission.
3. Apply budget/cost-tier admission when a request declares a ceiling.
4. Reject candidates whose circuit is open or whose rate-limit cooldown is active.
5. Execute the admitted candidate.
6. Classify failures by cause and update provider health state.
7. Advance only when the failure class is explicitly fallback-eligible.

## Budget policy

Provider/model profiles gain a Creation-owned cost tier. Requests may declare a maximum allowed tier. When a ceiling is present, unknown cost evidence fails closed. Budget metadata is admission evidence only; it cannot add providers to the candidate list or override governance.

Initial tiers are ordinal policy classes rather than invented dollar prices: `FREE`, `LOW`, `PREMIUM`, `FRONTIER`. A profile with no cost evidence is `UNKNOWN`.

## Circuit breaker

Circuit state is maintained per provider in memory for Phase 3: `CLOSED`, `OPEN`, `HALF_OPEN`.

Transient provider failures increment the failure counter. Crossing the configured threshold opens the circuit for a cooldown interval. After cooldown, one half-open probe is admitted. Success closes/reset the circuit; another transient failure reopens it.

Authentication, authorization, invalid local configuration, capability rejection, and budget rejection do not count as transient provider-health failures.

No distributed persistence is introduced in Phase 3.

## Rate-limit awareness

`InferenceRateLimitError` places the provider into a temporary cooldown. Requests during that cooldown skip the provider before network execution. This state remains Creation-owned and cannot authorize an unlisted provider.

## Cause-aware fallback

Fallback-eligible causes:
- provider rate limit / HTTP 429 equivalent already normalized by the adapter;
- timeout;
- transient upstream/server failure;
- provider temporarily unavailable/open circuit.

Fail-closed causes:
- authentication or authorization failure;
- invalid local/provider configuration;
- capability evidence rejection;
- budget rejection;
- malformed governance request.

Fallback always remains bounded by the explicit ordered candidate list. Registration or health of unrelated providers never makes them eligible.

## Security and governance invariants

- No automatic provider discovery.
- No implicit fallback.
- No fallback can bypass a capability or budget requirement.
- No provider credential is stored in health, budget, profile, telemetry, or frontend state.
- FreeLLMAPI remains an execution gateway, not a cognitive or governance authority.
- No tool-call execution is enabled as part of this phase.
- No fake production telemetry.

## Verification

Use TDD for budget admission, circuit transitions, cooldown behavior, 429/timeout/transient fallback, authentication fail-closed behavior, and the invariant that an unlisted provider is never selected. Then run Ruff, mypy, Alembic migrations, full pytest, frontend build/unit tests, and Playwright E2E. A phase-completion claim requires fresh green evidence from the complete CI gate.
