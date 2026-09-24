# Frozen Decisions — THE CREATION OS / Security Task Force

Status date: 2026-09-23

This file records design decisions already accepted by the Creator. They are not to be silently redesigned. A future change must explicitly supersede the affected decision and be recorded in `CHANGELOG_DECISIONS.md`.

## FD-001 — Creator remains the ultimate authority
The Creator declares intent and retains authority over decisions that exceed delegated mission authority. The system must not reinterpret silence as approval.

## FD-002 — Natural-language mission entry
The Creator does not manually assemble operational mission objects. The Creator states the intent in natural language; the Mission Compiler produces the structured mission contract.

## FD-003 — Separation of planes
Command, authorization, execution and evidence are separate concerns. No single component may silently combine all four powers.

## FD-004 — SOPHIA is Chief Architect
DEUS preserves Creator intent and chairs the decision flow. SOPHIA owns architectural synthesis, resolves structural conflicts and converts approved intent into coherent system design.

## FD-005 — Security Task Force is mission-oriented
The Security Task Force uses a small permanent core and summons specialist cells according to the mission. Permanent core: Mission Commander, Intel/Recon, Evidence/Verification. Summonable cells include Red, Blue, Purple, AppSec, Cloud, Identity, Container, Network and Forensics.

## FD-006 — Capability authority is ephemeral
Agents receive capability tokens scoped to mission, task, target, duration and action class. No agent inherits general operational authority merely because it participated in a prior mission.

## FD-007 — Scope never expands silently
A newly discovered asset can be added to the Target Graph as information. It does not become an executable target unless the mission contract authorizes it or the Creator explicitly expands scope.

## FD-008 — Red evidence is paired with defense evidence
Relevant offensive validation must preserve Attack Evidence and Defense Evidence. Purple correlation closes the finding before Verification can promote it to a confirmed result.

## FD-009 — Evidence precedes truth claims
Agent assertions alone are not findings. Findings are classified using reproducibility and evidence. Chronicle is append-only for mission evidence and decision history.

## FD-010 — Mission lifecycle is cancelable and bounded
Every operational mission requires timeout, resource bounds, checkpoints, cancellation semantics, idempotency where applicable, and a kill switch.

## FD-011 — Risk classes R0–R5
- R0: informational/read-only; automatic.
- R1: low-impact, safe and reversible; automatic inside approved scope.
- R2: controlled delegated action; allowed only when the mission grants that authority.
- R3: material state change or elevated impact; Creator approval.
- R4: sensitive/high-impact action; explicit Creator approval plus stronger evidence/rollback controls.
- R5: objective or scope expansion; compile as a new mission.

## FD-012 — Runtime stack direction
Approved architectural direction for the Security Task Force runtime: Python for cognition, Temporal for durable orchestration, NATS/JetStream for event transport, OPA for policy decisions, a Rust gateway at the privileged boundary, Kata Containers or Firecracker for isolated execution, and ATT&CK plus a graph representation for adversary/capability knowledge.

This is a design decision. Individual technologies can only be replaced by an explicit superseding decision, not by incidental implementation convenience.

## FD-013 — Cyber Range and Security Task Force are different systems
The Security Task Force is the operational team/capability. The Cyber Range is the isolated environment used for training, experimentation, replay and verification. The Range does not grant production authority.

## FD-014 — Promotion from Cyber Range requires verification
A Range experiment can only become an operational playbook after reproducible evidence, Verification, Chronicle recording, risk classification, rollback conditions and Mission Protocol authorization.

## FD-015 — SH-X is internal project certification
The ladder is SH-1 Qualified → SH-2 Advanced → SH-3 Elite → SH-X / Super Hacker Certified. SH-X is an internal qualification target of this project, not a claim of external professional accreditation.

## FD-016 — Cyber Range v1 must not be recreated blindly
Prior project context reports a completed v1 foundation consisting of Juice Shop, WebGoat/WebWolf bound to localhost, a Range Controller API, mission catalog, evidence journal, qualification rubric and start/stop/reset/verify scripts. During canonicalization, direct evidence for that reported state on current `main` has not yet been located. Therefore the next implementation session must verify the repository/runtime before changing or recreating the Range.

## FD-017 — Repository is the project memory
Canonical project state lives in version-controlled artifacts. Chat memory is supplementary. Before changing architecture or status, agents must read `CONTEXT_BOOTSTRAP.md`, `PROJECT_STATE.yaml`, this file and `ARCHITECTURE_GRAPH.yaml`.

## FD-018 — Implementation status must be evidence-based
The terms `DESIGN_APPROVED`, `IMPLEMENTED`, `TESTED`, and `VERIFIED_OPERATIONAL` are not interchangeable. A component is only promoted to a stronger status when repository/runtime evidence supports it.
