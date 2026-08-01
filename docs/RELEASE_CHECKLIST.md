# Release Checklist

Target: `v1.0.0-rc1`

This checklist is operational hardening only. It does not authorize new
features, architecture changes, services, engines, endpoints, workers, or
components.

## 1. Git State

```powershell
git branch --show-current
git status --short
git diff --check
```

Expected:

- branch is `main`;
- no accidental `.env`, SQL backup, log, cache, coverage, or local credential
  file is staged;
- whitespace check passes.

## 2. Environment

Create local configuration only when missing:

```powershell
Copy-Item .env.example .env
```

Required checks:

- `APP_SECRET_KEY` is a local secret and is not committed;
- `CREATOR_BOOTSTRAP_PASSWORD` is strong and is not committed;
- `DATABASE_URL` points to the application database;
- `TEST_DATABASE_URL` points to a disposable database whose name contains
  `test`;
- optional provider keys remain empty unless that connector is being validated.

## 3. Disposable Test Database

Integration tests are destructive. Use only `TEST_DATABASE_URL`.

```powershell
docker exec thecreationos-postgres-1 createdb -U postgres the_creation_os_test
```

If the database already exists, either reuse it as disposable or recreate it
intentionally. Never use `the_creation_os` for integration tests.

## 4. Backend Validation

```powershell
$env:TEST_DATABASE_URL='postgresql+asyncpg://postgres:postgres@localhost:5432/the_creation_os_test'
python -m pytest backend/tests -q
python -m ruff check backend
```

Expected:

- pytest passes;
- Ruff passes;
- no test writes to the application database.

## 5. Frontend Validation

```powershell
Set-Location frontend
npm run test
npm run build
Set-Location ..
```

Expected:

- TypeScript check passes;
- production build passes;
- `frontend/dist` remains untracked.

## 6. Docker Validation

```powershell
docker compose config
docker compose build
docker compose up -d --force-recreate
docker compose ps
```

Expected:

- Compose config renders successfully;
- API image builds;
- API is healthy;
- PostgreSQL is healthy;
- Redis is healthy;
- frontend container is up;
- `package-lock.json` is not modified by container startup.

## 7. Health Checks

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/v1/health/live
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/v1/health/ready
```

Expected:

- live returns `live`;
- ready returns `ready`;
- database revision is `0024_creator_singleton`;
- Redis responds.

## 8. Database Readiness

Read-only verification:

```powershell
docker exec thecreationos-postgres-1 psql -U postgres -d the_creation_os -t -A -c "SELECT version_num FROM alembic_version;"
```

Expected:

- `0024_creator_singleton`.

Do not truncate, seed, restore, or migrate the application database during
release validation unless explicitly authorized.

## 9. Critical Flow Smoke Review

Validate through API tests and Creator Interface:

- GOD Conversation;
- Voice;
- Mission Authorization;
- Capability Governance;
- Opportunity Discovery;
- Continuous Perception;
- Inception;
- Connector Execution;
- Chronicle;
- Audit trail;
- decisions;
- opportunities;
- active Mission display;
- responsive layout.

Physical microphone validation is operational. If hardware is unavailable,
record it as a release note rather than blocking automated validation.

## 10. Security Gate

```powershell
git status --short
git ls-files -- .env "*.sql" "backups/**" "*.log" "*.bak" "*.old" "*.tmp"
```

Expected:

- `.env` is not tracked;
- backups are not tracked except `backups/BACKUPS.md`;
- no logs, caches, coverage files, or temporary files are staged;
- no token, API key, password, private key, or credential value is committed.

## 11. Release Candidate Preparation

Do not create the RC tag until all checks pass and the Creator authorizes the
release.

Allowed after approval:

```powershell
git add .
git commit -m "chore(release): prepare v1.0.0-rc1"
```

Not allowed without explicit approval:

- tag creation;
- push;
- force push;
- database restore;
- destructive database cleanup;
- new feature work.
