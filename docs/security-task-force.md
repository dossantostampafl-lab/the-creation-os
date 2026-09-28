# Security Task Force

The Security Task Force runs Missions that are bound to explicitly authorized targets and environments. It reuses the
Creator, Mission, Chronicle and worker primitives of THE CREATION OS and adds an Authorization Plane, durable
orchestration, a privileged gateway and an evidence/verification chain.

## Flow

```
Creator -> API (/api/v1/deus/security-missions) -> Mission compiler -> ContractStore (hash-verified)
        -> Authorization Plane (local rules + OPA) -> ephemeral CapabilityGrant
        -> Temporal MissionWorkflow -> activities -> signed envelope -> Rust gateway -> isolated sandbox
        -> Range / target -> evidence (redacted, hashed) -> verification -> Chronicle
```

Command, authorization, execution and evidence stay separate: the API adapter can compile, ask, read and cancel but holds
no gateway or executor handle; only workflow activities dispatch, and only through the gateway.

## Invariants (each has a test)

- An environment id (`cyber_range:<zone>` or `real:<id>`) is carried by the contract, action, decision, grant, envelope,
  gateway request and evidence. Any mismatch denies.
- R3/R4 need a Creator approval reference; R5 is a new Mission, never an action in the current one.
- Grants are short-lived (default 5 min, max 30, never past the Mission window), single-use by default, revoked on
  cancel, and refused for a stale Mission version. Revocation, budget and kill state are persisted and re-read.
- With `STF_REQUIRE_POLICY=1` the API refuses to authorize unless `OPA_URL` is configured; otherwise the local rules apply alone.
- Every failure of policy, grant validation, state files, the gateway or the sandbox denies. None ever allows.
- A dispatch is at-most-once per idempotency key; a reservation that never completed is reported unknown, not repeated.
- The gateway refuses replayed nonces across restarts, tampered signatures/parameters, mismatched target, environment,
  action class or capability, and any environment prefix not listed in `STF_ALLOWED_ENVIRONMENTS` (default: Range only).
- There is no plain-Docker sandbox fallback: without Kata or Firecracker, privileged execution stays off while the
  control plane keeps running.
- The Cyber Range client refuses anything outside `cyber_range:*`. Success in the Range grants no real-environment authority.

## Running it

```bash
cp .env.example .env            # set STF_GATEWAY_SIGNING_KEY to 32+ random characters
docker compose --profile security-task-force up -d --build
docker compose -f cyber_range/compose.yml --profile cyber-range up -d   # optional, isolated Range
```

The core stack (`docker compose up`) never depends on any Task Force service.

## Status (evidence-based)

| Component | Status | Evidence |
|---|---|---|
| Contracts, compiler, authorization, grants, kill switch, ledger, events, evidence, verification | TESTED | `backend/tests/test_stf_*.py` (local + CI) |
| Adapter and HTTP routes, Chronicle correlation | TESTED | `test_stf_integration.py` incl. PostgreSQL |
| Rust gateway (validation, replay, TCP service) | TESTED | `cargo test`, clippy `-D warnings`, cross-language signature vector, `test_stf_e2e.py` against the real binary |
| Sandbox selection | TESTED (selection only) | `test_stf_modules.py`; no Kata/Firecracker adapter has run on a real host |
| Rego policy | IMPLEMENTED | decisions cross-checked with an independent Rego engine (regorus) for scope, approval, R5, unknown risk, stale version, expired/invalid window and empty input; the CI `opa` job (`check --strict` + `test`) is the authority and has not run yet |
| Temporal workflow | IMPLEMENTED | activities are tested; workflow tests need the Temporal test server and run in CI with `STF_REQUIRE_TEMPORAL=1` |
| Real-environment execution | NOT VERIFIED | no real environment has been exercised, and Range success does not imply it |
| SH-X | NOT AWARDED | the evaluator exists; no run has produced evidence for it |

Read the CI results on the exact final commit before promoting a status.
