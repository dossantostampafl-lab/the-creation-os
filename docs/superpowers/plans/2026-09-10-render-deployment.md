# Render Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make The Creation OS deployable on Render from the existing monorepo with a declarative Blueprint, correct API/worker/frontend runtime behavior, managed PostgreSQL/Redis references, and deterministic deployment invariants.

**Architecture:** Add a root `render.yaml` defining three application services plus managed data services. Keep Docker Compose behavior unchanged, give Render its own frontend serving configuration, and make API/worker startup explicit at the platform layer so backend application behavior remains unchanged.

**Tech Stack:** Render Blueprints, Docker, FastAPI/Uvicorn, Alembic, PostgreSQL/asyncpg, Redis, React/Vite, Nginx, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-10-render-deployment-design.md`

## Global Constraints

- Preserve `docker-compose.yml` local development behavior.
- Preserve `docker-compose.prod.yml` production Compose behavior.
- Preserve existing GitHub CI, release and security workflows.
- Do not change application-domain behavior.
- Do not commit real API keys, database passwords, creator credentials, or provider secrets.
- Production Render deployment must not silently select fake inference or fake embeddings.
- Render frontend must not depend on Docker Compose hostname `api:8000` or resolver `127.0.0.11`.
- API health path is `/api/v1/health/ready`.
- API must bind `0.0.0.0` and use Render `$PORT`.
- Worker must remain a background service with no public HTTP endpoint.

---

### Task 1: Add failing Render deployment invariants

**Files:**
- Create: `backend/tests/test_render_deployment_invariants.py`

**Interfaces:**
- Consumes: repository deployment files as plain text/YAML.
- Produces: deterministic static contract for all Render-specific files used by later tasks.

- [ ] **Step 1: Write the failing tests**

Create tests that resolve the repository root and assert:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_render_blueprint_exists() -> None:
    assert (ROOT / "render.yaml").is_file()


def test_render_blueprint_defines_required_services() -> None:
    text = (ROOT / "render.yaml").read_text()
    assert "creation-api" in text
    assert "creation-worker" in text
    assert "creation-frontend" in text
    assert "type: web" in text
    assert "type: worker" in text
    assert "type: pserv" in text
    assert "type: keyvalue" in text


def test_render_api_uses_port_and_health_contract() -> None:
    text = (ROOT / "render.yaml").read_text()
    assert "--host 0.0.0.0" in text
    assert "${PORT:-10000}" in text
    assert "/api/v1/health/ready" in text
    assert "python -m alembic upgrade head" in text


def test_render_frontend_is_not_bound_to_compose_dns() -> None:
    text = (ROOT / "frontend" / "nginx.render.conf").read_text()
    assert "api:8000" not in text
    assert "127.0.0.11" not in text
    assert "location /" in text
    assert "try_files $uri $uri/ /index.html" in text


def test_render_blueprint_has_no_fake_production_defaults() -> None:
    text = (ROOT / "render.yaml").read_text()
    assert "LLM_PROVIDER: fake" not in text
    assert "EMBEDDING_PROVIDER: fake" not in text


def test_render_blueprint_uses_managed_data_references() -> None:
    text = (ROOT / "render.yaml").read_text()
    assert "fromDatabase" in text
    assert "fromService" in text
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
cd backend
pytest -q tests/test_render_deployment_invariants.py
```

Expected: failures because `render.yaml` and `frontend/nginx.render.conf` do not yet exist.

- [ ] **Step 3: Commit RED test**

```bash
git add backend/tests/test_render_deployment_invariants.py
git commit -m "test(deploy): define Render deployment invariants"
```

---

### Task 2: Add Render Blueprint and managed service wiring

**Files:**
- Create: `render.yaml`
- Test: `backend/tests/test_render_deployment_invariants.py`

**Interfaces:**
- Consumes: `backend/Dockerfile`, `frontend/Dockerfile`, existing environment names from `backend/app/config.py` and inference provider loaders.
- Produces: Render Blueprint services `creation-api`, `creation-worker`, `creation-frontend`, `creation-postgres`, `creation-redis`.

- [ ] **Step 1: Create minimal Blueprint**

Define:

```yaml
services:
  - type: web
    name: creation-api
    runtime: docker
    rootDir: backend
    dockerfilePath: ./Dockerfile
    healthCheckPath: /api/v1/health/ready
    dockerCommand: >-
      sh -c 'python -m alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}'
    envVars:
      - key: APP_ENV
        value: production
      - key: APP_SECRET_KEY
        generateValue: true
      - key: CREATOR_BOOTSTRAP_USERNAME
        sync: false
      - key: CREATOR_BOOTSTRAP_PASSWORD
        sync: false
      - key: DATABASE_URL
        fromDatabase:
          name: creation-postgres
          property: connectionString
      - key: REDIS_URL
        fromService:
          type: keyvalue
          name: creation-redis
          property: connectionString
      - key: CORS_ALLOW_ORIGINS
        sync: false
      - key: LLM_PROVIDER
        sync: false
      - key: LLM_MODEL
        sync: false
      - key: LLM_API_KEY
        sync: false
      - key: FREELLMAPI_API_KEY
        sync: false
      - key: FREELLMAPI_MODEL
        sync: false
      - key: FREELLMAPI_BASE_URL
        sync: false
      - key: OPENAI_COMPATIBLE_API_KEY
        sync: false
      - key: OPENAI_COMPATIBLE_MODEL
        sync: false
      - key: OPENAI_COMPATIBLE_BASE_URL
        sync: false
      - key: EMBEDDING_PROVIDER
        sync: false
      - key: EMBEDDING_MODEL
        sync: false

  - type: worker
    name: creation-worker
    runtime: docker
    rootDir: backend
    dockerfilePath: ./Dockerfile
    dockerCommand: python -m app.worker
    envVars:
      - key: APP_ENV
        value: production
      - key: APP_SECRET_KEY
        fromService:
          type: web
          name: creation-api
          envVarKey: APP_SECRET_KEY
      - key: CREATOR_BOOTSTRAP_USERNAME
        fromService:
          type: web
          name: creation-api
          envVarKey: CREATOR_BOOTSTRAP_USERNAME
      - key: CREATOR_BOOTSTRAP_PASSWORD
        fromService:
          type: web
          name: creation-api
          envVarKey: CREATOR_BOOTSTRAP_PASSWORD
      - key: DATABASE_URL
        fromDatabase:
          name: creation-postgres
          property: connectionString
      - key: REDIS_URL
        fromService:
          type: keyvalue
          name: creation-redis
          property: connectionString
      - key: LLM_PROVIDER
        fromService:
          type: web
          name: creation-api
          envVarKey: LLM_PROVIDER
      - key: LLM_MODEL
        fromService:
          type: web
          name: creation-api
          envVarKey: LLM_MODEL
      - key: LLM_API_KEY
        fromService:
          type: web
          name: creation-api
          envVarKey: LLM_API_KEY
      - key: FREELLMAPI_API_KEY
        fromService:
          type: web
          name: creation-api
          envVarKey: FREELLMAPI_API_KEY
      - key: FREELLMAPI_MODEL
        fromService:
          type: web
          name: creation-api
          envVarKey: FREELLMAPI_MODEL
      - key: FREELLMAPI_BASE_URL
        fromService:
          type: web
          name: creation-api
          envVarKey: FREELLMAPI_BASE_URL
      - key: OPENAI_COMPATIBLE_API_KEY
        fromService:
          type: web
          name: creation-api
          envVarKey: OPENAI_COMPATIBLE_API_KEY
      - key: OPENAI_COMPATIBLE_MODEL
        fromService:
          type: web
          name: creation-api
          envVarKey: OPENAI_COMPATIBLE_MODEL
      - key: OPENAI_COMPATIBLE_BASE_URL
        fromService:
          type: web
          name: creation-api
          envVarKey: OPENAI_COMPATIBLE_BASE_URL
      - key: EMBEDDING_PROVIDER
        fromService:
          type: web
          name: creation-api
          envVarKey: EMBEDDING_PROVIDER
      - key: EMBEDDING_MODEL
        fromService:
          type: web
          name: creation-api
          envVarKey: EMBEDDING_MODEL

  - type: web
    name: creation-frontend
    runtime: docker
    rootDir: frontend
    dockerfilePath: ./Dockerfile.render
    healthCheckPath: /healthz
    envVars:
      - key: VITE_API_BASE_URL
        sync: false

databases:
  - name: creation-postgres
    databaseName: the_creation_os
    user: creation

# Render Blueprint schema should be verified against current Render docs before merge.
```

If current Render Blueprint schema uses a different key/value representation for Key Value service references, adjust to the current documented schema while preserving the same invariant: no hard-coded Redis hostname or secret.

- [ ] **Step 2: Run invariant tests**

```bash
cd backend
pytest -q tests/test_render_deployment_invariants.py
```

Expected: only frontend Render-specific configuration assertions may remain RED until Task 3; Blueprint assertions pass.

- [ ] **Step 3: Commit Blueprint**

```bash
git add render.yaml backend/tests/test_render_deployment_invariants.py
git commit -m "feat(deploy): add Render Blueprint"
```

---

### Task 3: Make frontend Render-native without breaking Compose

**Files:**
- Create: `frontend/Dockerfile.render`
- Create: `frontend/nginx.render.conf`
- Preserve: `frontend/Dockerfile`
- Preserve: `frontend/nginx.conf`
- Test: `backend/tests/test_render_deployment_invariants.py`

**Interfaces:**
- Consumes: `VITE_API_BASE_URL` build argument used by `frontend/src/api.ts`.
- Produces: Render-specific static frontend image on port 10000 with no Docker Compose DNS dependency.

- [ ] **Step 1: Add Render Nginx config**

```nginx
server {
    listen 10000;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    location = /healthz {
        access_log off;
        add_header Content-Type text/plain;
        return 200 'ok';
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 2: Add Render Dockerfile**

```dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN test -n "$VITE_API_BASE_URL" && npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.render.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 10000
```

The explicit `RUN test -n` prevents a production Render build from silently falling back to `http://localhost:8000/api/v1`.

- [ ] **Step 3: Run invariant tests**

```bash
cd backend
pytest -q tests/test_render_deployment_invariants.py
```

Expected: PASS.

- [ ] **Step 4: Build frontend Render image locally/CI**

```bash
docker build -f frontend/Dockerfile.render \
  --build-arg VITE_API_BASE_URL=https://example.invalid/api/v1 \
  frontend
```

Expected: build succeeds.

- [ ] **Step 5: Commit frontend Render path**

```bash
git add frontend/Dockerfile.render frontend/nginx.render.conf backend/tests/test_render_deployment_invariants.py
git commit -m "feat(frontend): add Render-specific runtime image"
```

---

### Task 4: Harden URL compatibility for Render-managed PostgreSQL

**Files:**
- Modify if required: `backend/app/config.py`
- Modify if required: `backend/app/db/session.py`
- Create/modify: `backend/tests/test_render_database_url.py`

**Interfaces:**
- Consumes: Render PostgreSQL `connectionString` value.
- Produces: SQLAlchemy-compatible async URL used by `create_async_engine`.

- [ ] **Step 1: Write URL compatibility test**

Test the exact transformation policy chosen from current Render connection string format. The desired result is that a conventional `postgresql://...` managed URL is normalized to `postgresql+asyncpg://...` while an already explicit SQLAlchemy driver URL is preserved.

```python
from app.db.url import normalize_database_url


def test_normalizes_render_postgres_scheme() -> None:
    assert normalize_database_url("postgresql://u:p@host/db") == "postgresql+asyncpg://u:p@host/db"


def test_preserves_explicit_asyncpg_scheme() -> None:
    value = "postgresql+asyncpg://u:p@host/db"
    assert normalize_database_url(value) == value
```

- [ ] **Step 2: Run RED**

```bash
cd backend
pytest -q tests/test_render_database_url.py
```

Expected: FAIL because `app.db.url` does not yet exist.

- [ ] **Step 3: Add minimal URL normalizer**

Create `backend/app/db/url.py`:

```python
def normalize_database_url(value: str) -> str:
    if value.startswith("postgresql://"):
        return "postgresql+asyncpg://" + value.removeprefix("postgresql://")
    return value
```

Update `backend/app/db/session.py`:

```python
from app.db.url import normalize_database_url

engine: AsyncEngine = create_async_engine(
    normalize_database_url(settings.database_url),
    future=True,
    echo=False,
)
```

- [ ] **Step 4: Run GREEN**

```bash
cd backend
pytest -q tests/test_render_database_url.py
```

Expected: PASS.

- [ ] **Step 5: Run existing database-related suite**

```bash
cd backend
pytest -q tests/test_render_database_url.py tests/test_release_invariants.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/url.py backend/app/db/session.py backend/tests/test_render_database_url.py
git commit -m "fix(db): accept managed PostgreSQL URLs"
```

---

### Task 5: Document safe Render variables and deployment flow

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Test: `backend/tests/test_render_deployment_invariants.py`

**Interfaces:**
- Consumes: Blueprint names and environment contract from Tasks 2–4.
- Produces: operator-facing Render setup instructions that distinguish generated/service-linked values from secrets the user must supply.

- [ ] **Step 1: Add Render documentation**

Document:

```text
Render Blueprint: render.yaml
Services: creation-api, creation-worker, creation-frontend
Data: creation-postgres, creation-redis
Required user values:
- CREATOR_BOOTSTRAP_USERNAME
- CREATOR_BOOTSTRAP_PASSWORD
- LLM_PROVIDER and provider-specific model/key/url
- EMBEDDING_PROVIDER and EMBEDDING_MODEL
- VITE_API_BASE_URL=https://<creation-api-host>/api/v1
- CORS_ALLOW_ORIGINS=https://<creation-frontend-host>
```

Explicitly state that `DATABASE_URL` and `REDIS_URL` come from managed service references and must not be copied from `.env.example`.

- [ ] **Step 2: Keep `.env.example` development-oriented but annotate production separation**

Add comments near local database/Redis/provider defaults explaining that these are local examples only and Render uses `render.yaml` plus platform secrets/service references. Do not add real credentials.

- [ ] **Step 3: Run static invariants**

```bash
cd backend
pytest -q tests/test_render_deployment_invariants.py
```

Expected: PASS.

- [ ] **Step 4: Commit documentation**

```bash
git add README.md .env.example backend/tests/test_render_deployment_invariants.py
git commit -m "docs: add Render deployment guide"
```

---

### Task 6: Add CI verification for Render deployment assets

**Files:**
- Modify: `.github/workflows/ci.yml`
- Test: existing GitHub Actions CI

**Interfaces:**
- Consumes: Render Blueprint and Dockerfiles from earlier tasks.
- Produces: automated verification that future changes cannot silently break Render deployment assets.

- [ ] **Step 1: Add release-job checks**

Extend the existing release job with:

```bash
cd backend
pytest -q tests/test_render_deployment_invariants.py tests/test_render_database_url.py
```

and Docker build:

```bash
docker build -f frontend/Dockerfile.render \
  --build-arg VITE_API_BASE_URL=https://example.invalid/api/v1 \
  frontend
```

Also parse `render.yaml` with a safe YAML parser available in CI, for example Python + PyYAML installed only for validation, or use Ruby's standard YAML if present. Assert top-level `services` and `databases` are parseable.

- [ ] **Step 2: Run local/static equivalent where available**

Run all new tests and both Docker builds.

- [ ] **Step 3: Commit CI gate**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: validate Render deployment assets"
```

---

### Task 7: Full regression and integration verification

**Files:**
- No new production files expected.
- Modify only defects discovered by verification, with their own failing regression test first.

**Interfaces:**
- Consumes: all earlier task outputs.
- Produces: merge-ready branch with fresh evidence.

- [ ] **Step 1: Run backend checks**

```bash
cd backend
ruff check .
mypy app
pytest -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend checks**

```bash
cd frontend
npm install
npm run build
npm test -- --run
npx playwright install chromium
npm run test:e2e
```

Expected: PASS.

- [ ] **Step 3: Build all relevant images**

```bash
docker build -t creation-backend:render backend
docker build -t creation-frontend:compose frontend
docker build -f frontend/Dockerfile.render \
  --build-arg VITE_API_BASE_URL=https://example.invalid/api/v1 \
  -t creation-frontend:render frontend
```

Expected: PASS.

- [ ] **Step 4: Verify Compose has not regressed**

```bash
docker compose -f docker-compose.prod.yml config --quiet
```

with the same explicit non-secret CI environment already used by the release workflow.

Expected: PASS.

- [ ] **Step 5: Open PR and wait for CI/security gates**

Create a PR from `feat/render-deployment` to `main`. Require backend, frontend, release and security jobs to be green before merge.

- [ ] **Step 6: Review changed files and secret exposure**

Verify no committed line contains actual provider keys, database passwords, creator passwords, or generated secret values.

- [ ] **Step 7: Merge only after fresh verification**

Merge after CI/release/security evidence is green. Re-fetch `main` and verify the merged commit status.
