# THE CREATION OS

Release-candidate baseline for the Creator-controlled operating layer.

The project contains a FastAPI backend, PostgreSQL persistence, Redis
infrastructure, and a React/Vite Creator Interface. The approved architecture is
preserved: Creator, GOD, SOPHIA, ROCKMAM, Inception, Central Core, Tree Core,
Agents, and Malkuth keep separate responsibilities.

## Current Release Baseline

- Branch target: `main`
- Release candidate target: `v1.0.0-rc1`
- Alembic head expected by readiness health check: `0024_creator_singleton`
- Backend: FastAPI, SQLAlchemy asyncio, Alembic, PostgreSQL 16 + pgvector, Redis
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

Install backend development tooling with `python -m pip install -e "./backend[dev]"`.

## Environment

Create local configuration from the example:

```powershell
Copy-Item .env.example .env
```

Generate the Git-ignored files in `secrets/` with the provided script (safe to
re-run; it never overwrites an existing non-empty file unless `-Force` is
passed):

```powershell
.\scripts\generate-secrets.ps1
```

This creates `app_secret_key.txt`, `creator_bootstrap_password.txt`,
`postgres_password.txt`, and `database_url.txt` (built from the same
PostgreSQL password, as required by `secrets/README.md`) with cryptographically
random values, plus empty placeholders for the optional
`elevenlabs_api_key.txt`, `github_token.txt`, and `llm_api_key.txt` — fill
those in only when enabling the corresponding integration.

For production, provision the declared Docker secret names from the deployment
platform or an external secret manager instead of running the script. Do not
bake secrets into images, Compose environment blocks, or `VITE_*` variables;
Vite values are public browser data.

Additional requirements:

- Keep `TEST_DATABASE_URL` pointed at a disposable database whose name contains `test`.
- Leave optional provider keys empty unless validating that connector.

Never commit `.env`, SQL backups, logs, coverage files, caches, or local
credential files.

## Docker Startup (reproducible from scratch)

This is the exact sequence to bring the stack up from nothing — no manual
database or secret steps beyond what is shown:

```powershell
Copy-Item .env.example .env   # skip if .env already exists
.\scripts\generate-secrets.ps1
docker compose config
docker compose down -v        # only if resetting an existing local volume
docker compose up --build -d
docker compose ps             # all four services must reach "healthy"
```

The API image applies Alembic migrations through its default `CMD`
(`python -m alembic upgrade head`) before starting `uvicorn` — there is no
separate migration step to run by hand. To apply migrations against a
different target manually, use the same single command from `backend/`:

```powershell
Set-Location backend
$env:DATABASE_URL = (Get-Content ..\secrets\database_url.txt -Raw)
python -m alembic upgrade head
python -m alembic current      # must print 0024_creator_singleton (head)
Set-Location ..
```

Verify the `vector` extension applied:

```powershell
docker compose exec postgres psql -U postgres -d the_creation_os -c "SELECT extname FROM pg_extension WHERE extname = 'vector';"
```

The frontend image uses a Node build stage and serves the compiled Vite assets
from an unprivileged Nginx runtime on container port 8080.

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
- `alembic_version.version_num` equal to `0024_creator_singleton`.

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

For startup failures, include stopped containers and inspect their exit state:

```powershell
docker compose ps -a
docker inspect (docker compose ps -aq) --format '{{.Name}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} error={{.State.Error}}'
docker compose logs --tail 200 api frontend postgres redis
```

Exit code 255 is not the conventional SIGKILL code (137). The inspect output
above distinguishes an application exit from an OOM kill or Docker daemon error.

## Shutdown

```powershell
docker compose down
```

Use `docker compose down -v` only when intentionally deleting local Docker
volumes.
