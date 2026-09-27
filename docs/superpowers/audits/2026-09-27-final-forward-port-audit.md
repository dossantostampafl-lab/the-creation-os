# Final forward-port branch audit

Date: 2026-09-27  
Production authority: `main` at `5e232ff79c9c7576812d3a209656d4afa72594b6`

## Decision

Both remaining branches are obsolete development lines and should be deleted after this audit is merged. Neither is safe to merge or cherry-pick wholesale. No file from either branch is currently used by `main`, Docker Compose, the Oracle deployment, or the production import graph.

The older opportunity/perception implementation is useful as a product concept, but not as deployable code: it belongs to a different model, repository, migration and worker architecture and would activate new external network behavior. Reintroducing that feature requires a separate design and TDD implementation against the current kernel; retaining two broken branches is not a safe substitute.

## Exact scope

| Branch | Audited tip | Behind / ahead of `main` | Three-dot diff | Verdict |
|---|---|---:|---:|---|
| `fix/creator-interface-living-functional-scene` | `523f34d34fdcbe21ccdb0350c63358a46ae496b9` | 643 / 55 commits | 351 files, +42,883/−149 | Original pre-canonical implementation; superseded |
| `restore/living-functional-core-forward-port` | `b6355749161376bcb7951f884ae3aaea9576576b` | 220 / 54 commits | 314 files, +38,661/−593 | Incomplete recovery attempt; abandoned and regressive |

The apparent small branch count was misleading. Relative to current `main`, 301 paths exist only on the first branch and 279 only on the recovery branch; 254 of those old-only paths overlap. The meaningful unit is therefore an obsolete subsystem tree, not a small set of independent files.

## Findings and evidence

### 1. Current orchestration already replaces the old execution stack

- Current `backend/app/worker.py:10-23` imports the governed capability gateway, provider router, kernel runtime, completion engine, reconciler, supervisor and projection refresher.
- Current `backend/app/worker.py:58-114` reconciles startup state and advances distributed/executing Missions through the current runtime.
- The recovery branch replaces that worker with the older dispatch protocol and a second family of repositories/services. Combining both would create two competing execution state machines.

**Fix:** keep the current kernel/worker and retire the duplicate stack.

### 2. The recovery branch removes production security and provider guarantees

- Current `backend/app/config.py:9-16` declares the supported provider chain.
- Current `backend/app/config.py:105-145` rejects published placeholder secrets, short production signing keys, fake fallback providers, unsupported providers and duplicate provider entries.
- Recovery `backend/app/config.py:10-75` omits all of those validations and omits the current fallback-provider configuration entirely.

**Fix:** do not port the recovery configuration. `main` remains authoritative.

### 3. The recovery Compose file would regress the live runtime

- Recovery `docker-compose.yml:45-50` hard-codes the PostgreSQL password to `postgres`.
- Recovery `docker-compose.yml:97-103` ends after the base network and removes the current Security Task Force services and isolated networks.
- Current `docker-compose.yml:46-53` obtains the password from configuration and preserves the existing named volume without setting a Compose project name.
- Current `docker-compose.yml:98-169` retains the opt-in NATS, OPA, Temporal, STF worker/gateway topology and its isolated networks.

**Fix:** reject the recovery Compose replacement. No project name, directory or volume is changed.

### 4. The recovery frontend is not reproducible and hides missing tests

- Recovery `frontend/package.json:10` restores `vitest run --passWithNoTests`.
- Recovery `frontend/package.json:16-34` uses unbounded `latest` versions and incorrectly places Vite/plugin runtime tooling in `dependencies`.
- The branch intentionally deleted `frontend/package-lock.json`; `npm ci` exits with `EUSAGE` before build or tests.
- Current `frontend/package.json:8-23` requires real tests and bounded dependency ranges; current CI runs build, Vitest and Playwright.

**Fix:** retain the current frontend toolchain and canonical living-DEUS UI.

### 5. The Alembic histories are incompatible

- Current production migrations form the `0001_initial` through `0009_semantic_cache` lineage.
- Recovery adds a separate `0010_ff_tree` through `0033_ff_reclaimed` lineage; for example recovery `backend/alembic/versions/0033_ff_reclaimed.py:28-31` depends on `0032_ff_memory_vector`.
- These migrations model the abandoned dispatch/repository family rather than the current kernel entities. Applying them to production would be a schema and behavior change, not cleanup.

**Fix:** do not copy any `_ff_` migration. A future feature must receive a new migration from the current `0009` head and prove upgrade/downgrade behavior against the current schema.

### 6. Opportunity/perception is conceptually unique but not safe to activate

- Recovery `backend/app/config.py:49-68` introduces opportunity thresholds, outbound perception intervals, Yahoo/GitHub sources and an allow-list.
- Recovery `backend/app/api/__init__.py:56-59` wires automation, opportunities and perception into the public API.
- No current production module imports these old models/services. Their database tables live only in the incompatible forward-port migration lineage.

**Fix:** preserve the concept in this audit only. Do not integrate dormant external polling or public routes as repository cleanup.

### 7. The old frontend is superseded, not missing

- The first branch's isolated frontend builds and its 38 Vitest assertions pass, proving it is internally coherent—not that it matches the current product contract.
- Current `CHANGELOG_DECISIONS.md:8` declares the living-DEUS dashboard, PWA behavior, Creator Decisions drawer and System Vitals drawer canonical.
- Current `frontend/src/App.tsx:193-305` implements the canonical live state, decisions and paginated vitals surface. The older component tree would replace rather than extend it.

**Fix:** retain current UI. Do not restore rejected screenshots, WebM recordings or frozen legacy component files.

### 8. Neither branch meets the repository quality gate

Commands were executed in isolated worktrees at the exact audited tips:

| Branch | Ruff | mypy | Backend test collection | Frontend |
|---|---|---|---|---|
| `523f34d` | pass | fail: 6 errors in 3 files | fail during collection/config import | `npm ci`, build and 38 Vitest tests pass |
| `b635574` | pass | fail: 12 errors in 5 files | fail during collection/config import | fail: no lockfile, so `npm ci` cannot run |

Representative failures include incompatible result types in `backend/app/agents/handlers.py`, missing annotations in `backend/app/repositories/scoped_memory.py`, nullable return typing in `backend/app/db/alembic_utils.py`, invalid dictionary indexing in `backend/app/kernel/orchestrator.py`, and invalid middleware kwargs in recovery `backend/app/main.py`.

**Fix:** do not weaken CI or tests. Retire the branches.

## Content disposition

| Content family | Disposition | Reason |
|---|---|---|
| Tree/Central Core, Malkuth, planner, dispatch, execution | Superseded | Current kernel, cognition, capabilities, Chronicle and worker implement the production path |
| Memory repositories and vector migrations | Superseded/incompatible | Current memory contracts, provenance and semantic-cache lineage are authoritative |
| Automation connectors | Superseded | Current governed web/workspace/PROTO capability adapters enforce authorization and bounded I/O |
| Opportunity/perception | Concept only | Unique idea, but stale implementation and new outbound behavior; not cleanup-safe |
| Legacy LivingDashboard components/assets | Superseded | Current living-DEUS PWA is the frozen product surface |
| Tests for the old subsystem family | Non-portable | They target removed schemas/services and do not collect cleanly on their own branch |
| SQL backups, screenshots and WebM evidence | Generated/historical | Not runtime inputs and should not be restored to `main` |
| Old docs and architecture notes | Superseded | Current root decisions, README and `docs/` runbooks govern production |

## Safe retirement procedure

1. Merge this documentation-only audit after normal CI and Security checks.
2. Delete each branch only after the remote ref still matches the audited full SHA.
3. Use a temporary, exact-SHA GitHub workflow because the connected API cannot directly delete refs.
4. Remove that workflow and its source branch immediately.
5. Confirm that `main` is the sole remote branch.

This procedure does not touch `.env`, secrets, Compose project naming, the Oracle directory, production volumes, deployment scripts or their invariant tests.
