# Mobile PWA Audit Baseline

**Captured:** 2026-09-26 14:29 UTC  
**Branch:** `feat/dashboard-living-presence`  
**Baseline plan commit:** `a972fa6a1b9fef6922766c0b46c9a2cd792d04c2`  
**Latest fetched `origin/main`:** `335bc2e2ddfcab94fbab59bea5fd936afbe2634c`

## Repository reconciliation

The branch started four commits ahead and one commit behind `origin/main`. The latest remote `main` was merged with the `ort` strategy without conflicts. After reconciliation the branch is five commits ahead and zero behind `origin/main`, with a clean working tree.

`git diff --check` passed before implementation.

## Toolchain

| Tool | Version / status |
|---|---|
| Git | 2.51.1 |
| Node.js | 24.19.0 |
| npm | 11.9.0 |
| Python | 3.12.14 |
| Docker | unavailable in this execution environment |

The backend development dependencies were installed into the plan-owned isolated virtual environment under `.superpowers/sdd/2026-09-26-mobile-pwa-finalization/venv`.

## Baseline results

| Area | Command | Result | Classification |
|---|---|---|---|
| Frontend production build | `npm run build` | PASS; 23 modules transformed; JS 237.12 kB, CSS 25.33 kB | clean baseline |
| Frontend unit tests | `npm test` | PASS; 1 file, 8 tests | clean baseline |
| Backend lint | `ruff check .` | PASS | clean baseline |
| Backend typing | `mypy app` | PASS; 124 source files | clean baseline |
| Backend pytest | `pytest -q` | BLOCKED; 62 setup errors and 1 failure after the database connection failed | unavailable infrastructure |
| Compose validation | `docker compose config --quiet` | NOT RUN; Docker executable absent | unavailable infrastructure |

## Backend failure investigation

The full traceback was inspected. The repeated root cause is an attempted connection to PostgreSQL on `localhost:5432`, rejected on both IPv6 and IPv4 with `Errno 111`. The environment has no Docker executable and no local PostgreSQL service, so database-backed fixtures cannot initialize. The single reported test failure occurs in the same database-backed projection integration path after connection setup fails; it is not independent evidence of a product assertion failure.

No production fix is justified from this environment-only failure. The complete Python suite, migrations, PostgreSQL/Redis integration, and Compose health checks remain mandatory release gates in CI or an environment that provides those services.

## Baseline conclusion

The source-only frontend and backend gates are green. Database-backed and container-runtime verification is deferred to the release gauntlet because the required infrastructure is unavailable locally; this limitation is explicit and must not be reported as a passing local test.
