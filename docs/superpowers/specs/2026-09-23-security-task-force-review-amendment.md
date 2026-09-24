# Security Task Force + Cyber Range — Phase 9 Review Amendment

Date: 2026-09-23  
Project: THE CREATION OS  
Branch: `feat/canonical-project-state`  
Status: **APPROVED NORMATIVE AMENDMENT**

This document is a normative amendment to `docs/superpowers/specs/2026-09-23-security-task-force-cyber-range-design.md`. Where the two documents differ on the points below, this amendment takes precedence. No other frozen architectural decision is reopened.

## A1 — MissionContract binds execution environment

`MissionContract` MUST include `authorized_environments` in addition to `authorized_targets`.

Minimum environment values are explicit identifiers such as `cyber_range:<scenario-or-zone>` or `real:<approved-environment-id>`. A grant or authorization issued for one environment MUST NOT be reusable in another environment.

Every privileged `ActionRequest`, `AuthorizationDecision`, `CapabilityGrant`, Rust Gateway validation and Chronicle evidence record MUST carry or resolve the same `environment_id`. A mismatch fails closed.

This implements DEC-2026-09-23-09 and preserves FD-007, FD-013, FD-014 and FD-019.

## A2 — Mission Compiler output is verifiable, not intrinsically deterministic

The Mission Compiler MAY use AI/reasoning internally. The implementation MUST NOT rely on identical model text or identical hidden reasoning across runs.

Its output MUST instead be:

- schema-valid;
- policy-valid;
- versioned;
- normalized before hashing/signing;
- reproducibly verifiable from the persisted contract and policy/version references;
- rejected when required authority, target or environment fields are ambiguous.

Therefore the Phase 3 acceptance phrase `natural-language intent → deterministic structured contract` is superseded by:

> natural-language intent → schema-valid, policy-valid, versioned and reproducibly verifiable structured contract.

This implements DEC-2026-09-23-09 without changing the approved mission states, R0–R5 risk model, escalation rules, dynamic team assembly, cancellation semantics or scope-expansion rules.

## A3 — Executor isolation decision remains delegated to SOPHIA

FD-020 remains in force. Implementation must perform a host-capability gate before selecting Kata Containers or Firecracker. If the current Windows/Docker Desktop host cannot provide the selected isolation boundary without weakening it, privileged execution remains disabled while the control plane, policy plane and non-privileged simulation continue to run. The implementation MUST NOT silently substitute a weaker sandbox.

## Review result

With A1–A3 incorporated as normative requirements, the written design is eligible for the Superpowers `writing-plans` handoff. Creation of the implementation plan does not authorize execution against any real system; real-environment authority remains mission-specific under FD-019.