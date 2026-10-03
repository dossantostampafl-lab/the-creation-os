# STF/Cyber Range Runtime Convergence Design

## Goal
Make PostgreSQL the canonical authority for live Security Task Force runs, then connect isolated execution, evidence, verification, Chronicle, and qualification without changing the already-approved STF/Cyber Range architecture.

## Existing truths
- Mission contracts, risk gates, OPA, Temporal, kill switch, Rust Gateway, RangeController, EvidenceRecord, verify_finding(), and qualification.evaluate() already exist.
- StfRepository already persists contracts, runs, grants, dispatches, approvals, inbox/outbox and provides reserve_dispatch()/record_outcome().
- The live worker still authorizes/dispatches through file-backed ContractStore/GrantStore/DispatchLedger.
- Kata/Firecracker adapters intentionally return NotImplemented.
- stf_verify_mission fails closed unless a verifier is injected.
- Cyber Range is isolated from production and remains training-only.

## Architecture decision
1. PostgreSQL is the canonical authority for any explicit run (run_id present).
2. File-backed stores remain only as compatibility support for legacy/file-only tests until migration is complete.
3. The worker must never spend authority outside the same database transaction that records the dispatch authorization.
4. The gateway receives only an already-reserved execution claim.
5. Execution remains fail-closed unless a supported isolated backend and allowlisted capability are available.
6. Evidence is correlated to run_id/action_id/execution_id/environment_id and verified before mission completion.
7. Qualification consumes immutable evidence references; no self-certification.
8. Cyber Range continues to refuse real:* environments.

## Gauntlet loop
PLAN → IMPLEMENT → TEST → AUDIT → ATTACK → FIX → RETEST → RE-AUDIT.

## Safety invariants
- No production target execution is introduced by this work.
- No Docker socket.
- No plain-Docker privileged fallback.
- No execution without contract + grant + reserve_dispatch.
- Unknown execution outcome is never retried automatically.
- Containment/policy/evidence-integrity failures remain disqualifying.
