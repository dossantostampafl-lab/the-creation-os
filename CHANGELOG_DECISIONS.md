# Decision Changelog

## 2026-09-23 — Canonicalization initiated

### DEC-2026-09-23-01 — Repository becomes canonical project memory
**Status:** accepted

The project will no longer depend on chat continuity alone. Canonical state is versioned in the repository through `PROJECT_STATE.yaml`, `FROZEN_DECISIONS.md`, `ARCHITECTURE_GRAPH.yaml`, this changelog and `CONTEXT_BOOTSTRAP.md`.

### DEC-2026-09-23-02 — Status vocabulary is explicit
**Status:** accepted

The project distinguishes `DESIGN_APPROVED`, `IMPLEMENTED`, `TESTED`, and `VERIFIED_OPERATIONAL`. Conversation claims are not silently promoted to implementation facts.

### DEC-2026-09-23-03 — Canonical branch rebased onto current main baseline
**Status:** accepted

The initial `feat/canonical-project-state` branch was first opened from `fix/creator-interface-living-functional-scene`. Comparison showed that legacy branch was 55 commits ahead and 463 commits behind current `main`, i.e. materially diverged. The canonical branch was therefore moved to current `main` at `dafc1edebf01b0ff583175fe91087ad2272fc0f2`. The legacy branch remains untouched for later reconciliation.

### DEC-2026-09-23-04 — Cyber Range v1 historical claim is preserved but marked for repository verification
**Status:** accepted

Prior project context reports the v1 isolated Range foundation as already completed, including Juice Shop, WebGoat/WebWolf localhost-only, Range Controller API, mission catalog, evidence journal, qualification rubric and lifecycle scripts. Current canonicalization has not yet located corresponding direct evidence on current `main`. The correct behavior is therefore **verify, do not recreate blindly**.

### DEC-2026-09-23-05 — Mission Protocol design is treated as closed
**Status:** accepted

The Creator supplies natural-language intent. The design flow is Creator → DEUS → Mission Compiler → SOPHIA → Authorization Plane → Mission Commander → Task Force → Verification → Chronicle → Creator. Risk classes R0–R5 and ephemeral capability authority are frozen design decisions unless explicitly reopened.

### DEC-2026-09-23-06 — Phase 9 has a formal review gate
**Status:** accepted

The phases 3–8 may be consolidated into a written design specification. The detailed executable Codex implementation plan is created only after the Creator reviews and approves that written specification. This prevents implementing against an unreviewed interpretation of the design.

### DEC-2026-09-23-07 — Security Task Force may operate in real explicitly authorized environments
**Status:** accepted

The Creator decided that the Security Task Force is not permanently restricted to the Cyber Range. After validation gates are satisfied, it may execute missions in real environments when the Creator explicitly authorizes the environment, target scope, mission objective and applicable risk ceiling. Authority is always mission-scoped and enforced through the Mission Contract, R0–R5 model, Authorization Plane, ephemeral capability grants, Rust Gateway, time window, target selector, rollback requirements and kill switches. R3/R4 retain Creator approval requirements; R5 remains a new mission. This is a design-only decision now and becomes an implementation requirement for the execution and authorization layers.

### DEC-2026-09-23-08 — Executor isolation choice delegated to SOPHIA
**Status:** accepted

The Creator delegated the final selection between Kata Containers and Firecracker to SOPHIA. SOPHIA must choose using isolation strength, host/local compatibility, performance, operational complexity, auditability, recovery behavior and least-privilege as criteria. The delegation does not reopen the Rust Gateway or Authorization Plane boundaries and does not authorize weaker isolation.

### DEC-2026-09-23-09 — Phase 3 Mission Protocol review approved
**Status:** accepted

The Creator approved Phase 3 after review. Two technical clarifications are mandatory in the next consolidated spec revision: (1) `MissionContract` must explicitly bind authorized execution environments in addition to authorized targets, preventing reuse of Range authorization in a real environment; and (2) the Mission Compiler may use AI/reasoning internally, but its output must be schema-valid, policy-valid, versioned and reproducibly verifiable rather than being described as intrinsically deterministic. These clarifications do not change the approved R0–R5 model, mission states, dynamic team assembly, escalation rules, kill-switch semantics or scope-expansion rules.

### DEC-2026-09-23-10 — Canonical resume checkpoint frozen at Phase 9
**Status:** accepted

The Creator explicitly froze the current project checkpoint at **Phase 9 — Creator specification review / Codex handoff gate**. Phases 1–8 and all frozen decisions remain closed to silent reinterpretation. Future sessions must resume from the Phase 9 review gate unless the Creator explicitly supersedes a prior decision. This checkpoint records continuity state only; it does not falsely promote unverified implementation claims.

Affected canonical file: `PROJECT_STATE.yaml`.

## Change procedure

A new decision entry must include:
1. date and stable decision id;
2. status (`proposed`, `accepted`, `superseded`, or `rejected`);
3. the old decision being replaced, when applicable;
4. rationale;
5. affected canonical files;
6. whether the change is design-only or requires code migration.

No agent may silently overwrite a frozen decision.
