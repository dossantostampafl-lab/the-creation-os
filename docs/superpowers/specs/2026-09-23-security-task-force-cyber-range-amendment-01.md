# Security Task Force + Cyber Range — Binding Amendment 01

Date: 2026-09-23  
Project: THE CREATION OS  
Branch: `feat/canonical-project-state`  
Applies to: `docs/superpowers/specs/2026-09-23-security-task-force-cyber-range-design.md`  
Source decision: `DEC-2026-09-23-09`

## Status

**DESIGN_APPROVED — binding clarification for implementation planning.**

This amendment does not reopen Phases 1–8. It corrects two statements in the consolidated design specification before the Phase 9 implementation plan is executed.

## A1 — MissionContract binds execution environment

The `MissionContract` MUST include:

- `authorized_environments`

Allowed environment identities are explicit values, not inferred from target identity. At minimum the implementation must distinguish:

- `CYBER_RANGE`
- `REAL_AUTHORIZED`

An authorization, capability grant, or action request issued for `CYBER_RANGE` MUST NOT be reusable in `REAL_AUTHORIZED`, even when the target identifier or capability name is otherwise identical.

The tuple used for authorization and replay protection therefore includes at least:

`mission_id + mission_version + actor + target + environment + capability/action_class + expiry + action/idempotency identity`

## A2 — Mission Compiler output is verifiable, not assumed deterministic

The Mission Compiler MAY use AI/reasoning internally. The implementation must not rely on the model output being intrinsically deterministic.

A compiled mission is acceptable only when the resulting `MissionContract` is:

1. schema-valid;
2. policy-valid;
3. explicitly versioned;
4. bound to authorized targets and execution environments;
5. validated against the R0–R5 risk model;
6. reproducibly verifiable from the stored input, compiler/version metadata, normalized contract, and validation evidence.

Accordingly, the Phase 3 acceptance phrase `natural-language intent → deterministic structured contract` is superseded by:

> natural-language intent → schema-valid, policy-valid, versioned and reproducibly verifiable structured contract.

## A3 — Implementation consequences

The Phase 9 plan must include tests proving all of the following:

- a Range-only grant is rejected in a real authorized environment;
- an environment omitted from `authorized_environments` is denied;
- compiler output that fails schema or policy validation never reaches authorization;
- re-running verification against the stored normalized contract produces the same validation result even when the upstream reasoner is non-deterministic;
- mission version changes invalidate grants issued for the previous version.

## Precedence

When wording in the original design specification conflicts with this amendment, this amendment and `FROZEN_DECISIONS.md` take precedence. All other parts of the original specification remain unchanged.
