# Context Bootstrap — Mandatory Project Start

This file is the startup contract for ChatGPT, Codex and any other agent working on THE CREATION OS.

## 1. Read before changing anything

Read in this order:

1. `PROJECT_STATE.yaml`
2. `FROZEN_DECISIONS.md`
3. `ARCHITECTURE_GRAPH.yaml`
4. `CHANGELOG_DECISIONS.md`
5. `ARCHITECTURE.md`
6. the spec or audit document for the subsystem being changed
7. current repository code and tests

Do not start from conversation memory when these sources are available.

## 2. Resolve state using evidence tiers

Use the following hierarchy:

- **Tier A — runtime/repository evidence:** code, migrations, tests, compose state, CI, logs, reproducible commands.
- **Tier B — canonical state:** `PROJECT_STATE.yaml` and frozen decisions.
- **Tier C — reviewed design specs and audit docs.**
- **Tier D — conversation history/memory.**

When two tiers conflict, never invent a reconciliation. Record the conflict and use the higher-evidence tier for implementation claims while preserving lower-tier design intent until the Creator resolves it.

## 3. Use exact status language

Allowed status labels:

- `PROPOSED`
- `DESIGN_APPROVED`
- `IMPLEMENTED`
- `TESTED`
- `VERIFIED_OPERATIONAL`
- `DEPRECATED`
- `SUPERSEDED`

Never use "done", "ready", "100%", or equivalent as a substitute for these labels unless the exact acceptance criteria and evidence are stated.

## 4. Never reopen frozen decisions silently

If a task appears to require changing a decision in `FROZEN_DECISIONS.md`:

1. identify the affected decision id;
2. explain the incompatibility;
3. create a proposed superseding decision;
4. do not modify implementation until the Creator approves that supersession.

## 5. Mission and security invariants

- Creator is the final escalation authority.
- Natural-language intent is compiled into a mission contract.
- Command, authorization, execution and evidence remain separated.
- Capability authority is ephemeral and scope-bound.
- New discoveries do not automatically expand executable scope.
- R3/R4 require Creator approval; R5 becomes a new mission.
- Cyber Range does not grant production authority.
- Findings require reproducible evidence.
- Operational authority expires; validated knowledge may persist.

## 6. Cyber Range startup rule

Prior context reports Cyber Range v1 as already implemented, but current `main` evidence has not yet been reconciled during canonicalization. Therefore:

**Do not create a new Range from scratch until you first search the current repository, legacy branch(es), Docker assets and commit history for the existing Range implementation.**

If found, reconcile or migrate it. If not found, record that evidence gap before proposing recreation.

## 7. Git rules

- Work on a dedicated branch/worktree.
- Do not mutate `main` directly.
- Never force-move or delete a non-disposable project branch unless the Creator explicitly asks.
- The canonical documentation branch is `feat/canonical-project-state`.
- Legacy branch `fix/creator-interface-living-functional-scene` is known to diverge from `main`; preserve it until reconciliation is complete.

## 8. Phase gate

Current program design runs through Phase 9.

- Phases 1–2: closed.
- Phase 3: Mission Protocol design approved.
- Phases 4–8: consolidated in the current written design spec.
- Phase 9: Codex handoff; executable implementation plan is generated only after Creator review of the written spec.

## 9. End-of-session update

Before finishing a material project session:

1. update `PROJECT_STATE.yaml` if status changed;
2. update `CHANGELOG_DECISIONS.md` for any accepted/superseded decision;
3. update `ARCHITECTURE_GRAPH.yaml` if relationships changed;
4. add evidence links/commands to the relevant audit/spec;
5. leave the repository in a state where the next session can resume without reconstructing chat history.
