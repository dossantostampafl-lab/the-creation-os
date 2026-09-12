# PROTO Secure Bridge Design

## Goal
Wire THE CREATION OS to the existing PROTO Creation bridge without exposing arbitrary PROTO endpoints or financial execution.

## Scope
- Add a single outbound capability adapter in THE CREATION OS for PROTO safe missions.
- Register the adapter only when PROTO bridge configuration is complete.
- Keep the existing CapabilityRuntime authorization/audit boundary intact.
- Keep the PROTO allowlist authoritative: `market-data-health`, `opportunity-scan`, `shadow-decision`.
- Preserve `financial_connectivity=false` and `real_money_execution=false` as bridge invariants.
- Add deterministic tests for configuration, request mapping, secret handling, response validation, failures, and worker registration.
- Do not add broker/exchange execution to THE CREATION OS.

## Architecture
THE CREATION OS remains the caller and PROTO remains the execution boundary for safe research/monitoring jobs:

Creator -> DEUS -> Mission -> Agent -> CapabilityRuntime -> ProtoCapabilityAdapter -> PROTO `/creation/missions` -> ProtoBrain.

The adapter is a narrow HTTP client. It accepts only `capability="proto"` and action `submit_mission`; it maps intent arguments into PROTO's existing Mission v1 contract. The base URL and shared secret come exclusively from process configuration, never from `CapabilityIntent.arguments`, so an agent cannot redirect requests to an arbitrary host or inject credentials into persisted invocation JSON.

## Security Constraints
1. Production requires an `https://` PROTO base URL.
2. Shared secret is stored as `SecretStr` and is only inserted into the outbound `X-Proto-Creation-Token` header.
3. Intent arguments cannot override the configured URL, token, transport headers, or safe job allowlist.
4. Only execution modes `LIVE_MONITORING`, `SIMULATION`, `PAPER_TRADING`, and `HISTORICAL_REPLAY` are accepted by the adapter. Financial live modes are rejected locally.
5. Only the three safe bridge jobs are accepted locally, in addition to PROTO's own server-side allowlist.
6. HTTP timeout is explicit; redirects are disabled; response JSON must validate required bridge invariants.
7. Secrets are never written to CapabilityInvocation request/result/error payloads.
8. POST retries are not performed by the adapter. Mission idempotency is supplied by a stable mission UUID and PROTO's durable `mission:{mission_id}:{job}` key.
9. Adapter failures return/raise sanitized errors without response bodies or credentials.

## Configuration
New settings:
- `PROTO_BASE_URL`: optional fixed service origin.
- `PROTO_CREATION_SHARED_SECRET`: optional secret.
- `PROTO_TIMEOUT_SECONDS`: positive float, default 10.

The adapter is enabled only when both base URL and secret are present. Production configuration rejects non-HTTPS origins.

## Capability Contract
CapabilityIntent:
- `capability`: `proto`
- `action`: `submit_mission`
- `arguments.mission_id`: UUID string
- `arguments.objective`: 1..2000 chars
- `arguments.requested_jobs`: non-empty list of safe job names
- `arguments.execution_mode`: safe non-financial mode
- optional `priority`, `scope`, `constraints`, `deadline`

Result data contains the validated PROTO MissionReceipt fields. It does not contain the shared secret or transport metadata.

## Error Handling
- Missing adapter/configuration: existing `LookupError` behavior remains fail-closed.
- Contract violations: `ValueError` before network I/O.
- Timeout/network/HTTP/non-JSON/invariant violations: sanitized adapter exception; CapabilityRuntime persists the class name but not sensitive bodies.

## Testing
TDD tests prove:
- configuration enables/disables adapter correctly;
- production HTTP origin is rejected;
- only safe jobs/modes can be submitted;
- caller-provided URL/token fields are ignored/rejected;
- correct PROTO path/header/payload is emitted;
- shared secret never appears in CapabilityResult;
- financial-connectivity invariant violations are rejected;
- worker gateway registration is deterministic.

Existing backend CI, stack gate, release gate and Security workflows remain mandatory before merge.

## Out of Scope
- PROTO real-money trading adapters.
- Broker credentials.
- Arbitrary PROTO job execution.
- Re-architecting the kernel or capability runtime.
- Changing PROTO's existing server-side bridge in this change unless a cross-contract defect is proven by tests.
