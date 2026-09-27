# Final Forward-Port Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine whether either remaining divergent branch contains safe, necessary work and retire only branches proven obsolete.

**Architecture:** Treat `main` as the production authority and compare both branch trees, histories, runtime entry points, migrations, dependency manifests and quality gates against it. Preserve reusable ideas in an evidence-backed audit; do not merge stale implementations into the current kernel.

**Tech Stack:** Git, FastAPI, PostgreSQL/Alembic, React/Vite, Docker Compose, Ruff, mypy, pytest, Vitest.

**Spec:** User request in the 2026-09-27 repository-cleanup session.

## Global Constraints

- Never commit `.env` or secrets; `.env.example` remains placeholders only.
- Never set a Compose project name or rename the production project directory.
- Do not weaken deployment invariant tests or replace `env_set` with regex/sed writes.
- Do not integrate code that changes production behavior merely to preserve an old branch.
- Delete a branch only after its exact tip and retirement evidence are recorded.

## Review Focus

- A stale branch must not replace current security/provider validation.
- A stale Alembic lineage must not be grafted onto the current production database.
- Old UI assets must not displace the canonical living-DEUS surface.
- Experimental external perception must not become active without a separate product decision.
- Branch deletion must verify the exact audited commit SHA.

---

### Task 1: Inventory and classify both branches

**Files:**
- Create: `docs/superpowers/audits/2026-09-27-final-forward-port-audit.md`

**Interfaces:**
- Consumes: `origin/main`, `origin/fix/creator-interface-living-functional-scene`, `origin/restore/living-functional-core-forward-port`.
- Produces: an evidence-backed keep/port/retire decision.

- [x] Record merge bases, divergence, changed-file counts and exact tip SHAs.
- [x] Compare runtime wiring, migrations, Compose, dependencies and frontend contracts.
- [x] Run Ruff/mypy and backend collection checks on both tips.
- [x] Run frontend clean-install/build/tests where the branch permits it.
- [ ] Commit the audit as a documentation-only change.

### Task 2: Verify current main and publish the audit

**Files:**
- Modify: none beyond Task 1 documentation.

**Interfaces:**
- Consumes: Task 1 retirement decision.
- Produces: a reviewable PR with green CI.

- [ ] Run current-main Ruff, mypy, frontend tests and build.
- [ ] Open one documentation-only PR and wait for all repository checks.
- [ ] Merge only after CI and Security succeed.

### Task 3: Retire exact stale refs

**Files:**
- Create then remove: a temporary SHA-verifying GitHub Actions workflow.

**Interfaces:**
- Consumes: the exact tips recorded in Task 1.
- Produces: `main` as the only remaining remote branch.

- [ ] Delete `fix/creator-interface-living-functional-scene` only if its tip still matches the audited SHA.
- [ ] Delete `restore/living-functional-core-forward-port` only if its tip still matches the audited SHA.
- [ ] Delete the temporary workflow and its source branch.
- [ ] Confirm the final remote branch inventory and final `main` SHA.
