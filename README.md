# THE CREATION OS

Release-candidate baseline for the Creator-controlled operating layer.

The project contains a FastAPI backend, PostgreSQL persistence, Redis
infrastructure, and a React/Vite Creator Interface. The approved architecture is
preserved: Creator, GOD, SOPHIA, ROCKMAM, Inception, Central Core, Tree Core,
Agents, and Malkuth keep separate responsibilities.

## Current Release Baseline

- Branch target: `main`
- Release candidate target: `v1.0.0-rc1`
- Alembic head expected by readiness health check: `0021_mission_authorization`
- Backend: FastAPI, SQLAlchemy asyncio, Alembic, PostgreSQL 16, Redis
- Frontend: React, Vite, TypeScript

## Architecture Rules

- Only the Creator controls GOD.
- Conversation does not create Mission.
- Inception does not create Mission automatically.
- Mission authorization remains explicit.
- Tree Core selects, dispatches, consolidates, and returns data only within its approved boundaries.
- Central Core records decisions; it does not manifest.
- Malkuth remains responsible for manifestation.
- Connectors stay behind capability governance.

## Prerequisites

- Docker and Docker Compose
- Python 3.12 or newer, below 3.15
- Node.js 20 for local frontend work
- Git

## Environment

Create local configuration from the example:

```powershell
Copy-Item .env.example .env
```

Required local changes:

- Set `APP_SECRET_KEY` to a long random value.
- Set `CREATOR_BOOTSTRAP_PASSWORD` to a strong local password.
- Keep `TEST_DATABASE_URL` pointed at a disposable database whose name contains `test`.
- Leave optional provider keys empty unless validating that connector.

Never commit `.env`, SQL backups, logs, coverage files, caches, or local
credential files.

## Docker Startup

```powershell
docker compose config
docker compose build
docker compose up -d --force-recreate
docker compose ps
```

The API container applies Alembic migrations on startup. The frontend container
uses `npm ci` so the lockfile is not rewritten during container startup.

## Health Checks

Live check:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/v1/health/live
```

Readiness check:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/v1/health/ready
```

Readiness requires:

- PostgreSQL reachable;
- Redis reachable;
- `alembic_version.version_num` equal to `0021_mission_authorization`.

## Tests

Frontend:

```powershell
Set-Location frontend
npm run test
npm run build
Set-Location ..
```

Backend integration tests are destructive against `TEST_DATABASE_URL` only. Do
not point `TEST_DATABASE_URL` at `the_creation_os`.

```powershell
$env:TEST_DATABASE_URL='postgresql+asyncpg://postgres:postgres@localhost:5432/the_creation_os_test'
python -m pytest backend/tests -q
python -m ruff check backend
git diff --check
```

## Release Readiness Command Set

Run this sequence before preparing `v1.0.0-rc1`:

```powershell
python -m pytest backend/tests -q
Set-Location frontend
npm run test
npm run build
Set-Location ..
python -m ruff check backend
git diff --check
docker compose config
docker compose build
docker compose up -d --force-recreate
docker compose ps
```

The detailed release checklist is maintained in
`docs/RELEASE_CHECKLIST.md`.

## Critical Flows To Validate

- GOD Conversation
- Voice
- Mission Authorization
- Capability Governance
- Opportunity Discovery
- Continuous Perception
- Inception
- Connector Execution
- Chronicle
- Audit trail
- Creator Interface responsiveness

Physical microphone validation is operational and must be confirmed manually
when audio hardware is available.

## Local Addresses

- Frontend: http://127.0.0.1:5173
- Backend API: http://127.0.0.1:8000/api/v1
- Readiness: http://127.0.0.1:8000/api/v1/health/ready

## Logs

```powershell
docker compose logs api
docker compose logs frontend
docker compose logs postgres
docker compose logs redis
```

## Shutdown

```powershell
docker compose down
```

Use `docker compose down -v` only when intentionally deleting local Docker
volumes.
