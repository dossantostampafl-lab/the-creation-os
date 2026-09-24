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

## Change procedure

A new decision entry must include:
1. date and stable decision id;
2. status (`proposed`, `accepted`, `superseded`, or `rejected`);
3. the old decision being replaced, when applicable;
4. rationale;
5. affected canonical files;
6. whether the change is design-only or requires code migration.

No agent may silently overwrite a frozen decision.
