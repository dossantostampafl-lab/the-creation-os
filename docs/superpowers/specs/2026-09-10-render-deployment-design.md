# Render Deployment Design — The Creation OS

Date: 2026-09-10
Status: Approved design for implementation

## Goal

Make The Creation OS deployable on Render from the existing monorepo without breaking the current Docker Compose development/production paths or the existing GitHub CI/release gates.

## Current constraints

The repository is a monorepo with `backend/` and `frontend/` subdirectories. The existing production topology assumes Docker Compose service DNS (`api`, `postgres`, `redis`) and therefore cannot be mapped to Render unchanged. The backend Docker image has no default command, the frontend Nginx configuration assumes Docker's embedded resolver and `api:8000`, and production runtime configuration is externalized through environment variables.

## Selected architecture

Use a Render Blueprint in the repository root and deploy five managed components:

1. `creation-api` — Render Web Service, Docker, root directory `backend`.
2. `creation-worker` — Render Background Worker, Docker, root directory `backend`.
3. `creation-frontend` — Render Web Service, Docker, root directory `frontend`.
4. Managed Render PostgreSQL.
5. Managed Render Key Value/Redis.

The frontend will call the API using an explicit build-time `VITE_API_BASE_URL` pointing to the Render API public URL. The backend will allow only the configured frontend origin through `CORS_ALLOW_ORIGINS`. This avoids depending on Docker Compose service DNS or Docker's `127.0.0.11` resolver inside Render.

## API service

The API service uses `backend/Dockerfile` and starts with a Render-specific command that runs database migrations and then Uvicorn:

`sh -c 'python -m alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}'`

Health check path: `/api/v1/health/ready`.

Required runtime configuration remains fail-closed. Secrets are injected by Render and never committed.

## Worker service

The worker uses the same backend Docker image and runs:

`python -m app.worker`

It receives the same database, Redis, inference, embedding and application environment as the API, except that it exposes no HTTP port.

## PostgreSQL and Redis

Use Render-managed services. `DATABASE_URL` and `REDIS_URL` are injected from Blueprint/service references rather than hard-coded hostnames. The application continues to use async SQLAlchemy/asyncpg and Redis exactly as it does today.

## Frontend service

The frontend continues to build with Vite and serve static assets through Nginx. For Render, the API base URL is injected at build time through `VITE_API_BASE_URL`. The Render-specific frontend Nginx configuration serves the SPA and `/healthz` but does not proxy `/api` through Docker Compose hostnames.

The existing Docker Compose frontend behavior remains available for Compose by preserving a Compose-specific Nginx configuration or build mode rather than weakening the Render path.

## Environment and secrets

Blueprint-managed non-secret values:

- `APP_ENV=production`
- token/session defaults
- log level
- provider selection keys where appropriate

User-supplied/generated secret values:

- `APP_SECRET_KEY`
- `CREATOR_BOOTSTRAP_USERNAME`
- `CREATOR_BOOTSTRAP_PASSWORD`
- provider API credentials

Managed service references:

- `DATABASE_URL`
- `REDIS_URL`

The design does not commit real API keys or database credentials.

## Inference and embeddings

Operational deployments must not silently fall back to `fake`. The Blueprint should require explicit inference and embedding configuration, while allowing the user to choose among the already-supported providers. Provider-specific URLs/models/keys remain optional until that provider is selected, at which point existing application configuration fails closed if required values are missing.

## Compatibility

The implementation must preserve:

- `docker-compose.yml` local development behavior.
- `docker-compose.prod.yml` production Compose behavior.
- existing GitHub CI, release and security workflows.
- existing Intelligence Fabric routing and provider invariants.
- existing frontend E2E semantics.

No application-domain behavior is changed by this deployment work.

## Tests and verification

Add deterministic deployment-invariant tests that verify at minimum:

- `render.yaml` exists and defines API, worker, frontend, PostgreSQL and Redis.
- API uses the Render `$PORT` contract.
- API health check points to `/api/v1/health/ready`.
- worker has no public web service role.
- Render frontend does not depend on `api:8000` or Docker resolver `127.0.0.11`.
- frontend production API URL is explicit and does not fall back to localhost.
- Render database/Redis values come from service references, not committed credentials.
- fake inference defaults are not declared for the production Blueprint.
- no secret material is added to the repository.
- existing Docker Compose release-invariant tests continue to pass.

Verification gate before merge:

1. backend unit/integration suite relevant to deployment.
2. frontend build and unit/E2E tests.
3. Docker build for backend and frontend.
4. static validation of `render.yaml` and deployment invariants.
5. existing GitHub CI/release/security workflows green on the branch/PR.

## Success criteria

The repository is considered Render-ready when a user can create the Blueprint from GitHub, supply only the secrets/provider choices that cannot safely be committed, and Render can build/start all application services with correct database, Redis, health, CORS and frontend/API connectivity settings, without manual repair of repository paths or Docker Compose assumptions.
