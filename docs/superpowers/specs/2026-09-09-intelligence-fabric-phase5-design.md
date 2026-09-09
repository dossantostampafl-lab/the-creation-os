# Intelligence Fabric Phase 5 — Evidence-Ranked Routing and Generic OpenAI-Compatible Provider

**Status:** Approved continuation of the Intelligence Fabric rollout.

## Goal

Finish the Intelligence Fabric with two bounded capabilities that preserve Creation-owned governance:

1. optional evidence-ranked selection among providers already explicitly authorized by the request; and
2. a generic OpenAI-compatible provider for local/direct gateways without coupling the cognitive core to a vendor.

## Routing Decision

The existing ordered preferred/fallback behavior remains the default. Evidence-ranked routing is opt-in through `ModelRequirements.routing_strategy="benchmark"`.

Benchmark routing MUST NOT discover providers. The candidate set is still exactly `preferred_provider` followed by explicitly listed `fallback_providers`. The router may only reorder that authorized set.

A `ProviderBenchmarkEvidence` record contains provider, model, suite id, score, sample count and observation timestamp. Evidence is immutable and operator/test supplied; the runtime never invents scores. Candidates without matching evidence remain behind evidenced candidates while preserving original order. Ties preserve original order.

Capability and budget admission remain fail-closed and apply before network execution. Benchmark routing does not bypass health, circuit breaker, cooldown, authentication or configuration failures.

## Generic OpenAI-Compatible Provider

Add `OpenAICompatibleProvider` implementing the existing `ModelProvider` contract against:

- `POST {base_url}/chat/completions`
- `GET {base_url}/models`
- SSE streaming using OpenAI-compatible `data:` frames.

Configuration is fail-closed when `LLM_PROVIDER=openai_compatible`:

- `OPENAI_COMPATIBLE_BASE_URL` required and limited to http/https.
- `OPENAI_COMPATIBLE_MODEL` required.
- `OPENAI_COMPATIBLE_API_KEY` optional so authenticated direct gateways and unauthenticated local runtimes are both supported.
- `OPENAI_COMPATIBLE_TIMEOUT_SECONDS` must be > 0.

No request metadata, prompt content, upstream response body or credentials may enter normalized error messages or telemetry.

## Registry and Evidence

`ProviderRegistry` stores immutable benchmark evidence keyed by `(provider, model)`. Duplicate evidence for the same provider/model/suite is rejected. The router only reads evidence; governance authorization still comes exclusively from request requirements.

## Verification

TDD must prove:

- ordered routing remains unchanged by default;
- benchmark mode reorders only explicitly authorized candidates;
- candidates are not implicitly discovered;
- missing benchmark evidence never creates a fabricated score;
- capability/budget gates remain enforced;
- OpenAI-compatible generate/stream/health and failure normalization work;
- bootstrap fails closed on missing/invalid configuration;
- full backend and frontend CI remains green.
