# Testing

## Backend integration tests

Backend integration tests are destructive against `TEST_DATABASE_URL` only.
Do not point `TEST_DATABASE_URL` at `the_creation_os` (the application
database).

```powershell
$env:TEST_DATABASE_URL='postgresql+asyncpg://postgres:postgres@localhost:5432/the_creation_os_test'
python -m pytest backend/tests -q
```

## `postgres-test`: a faster Postgres for local test runs

`docker-compose.yml` defines a second, isolated Postgres service,
`postgres-test`, purpose-built for running the backend test suite locally.
See `ARCHITECTURE.md`, "Investigação da lentidão da suíte de testes", for
the full investigation: on this project's Docker Desktop/WSL2 development
host, raw disk `fsync` was measured at roughly 300ms per write (a `dd ...
oflag=dsync` benchmark took 60.78s for 1.6MB), and the test suite's
per-fixture `TRUNCATE` calls pay that cost on every test because the
Postgres used for testing had the same durability settings as production.
`postgres-test` disables that durability for a ~8.4x speedup, without
touching the real `postgres` service at all.

### What it is

- Same image as the main `postgres` service (`pgvector/pgvector:pg16`).
- Own container, own port (`5433`, not `5432`), own named volume
  (`postgres_test_data`, not `postgres_data`) — fully isolated from the
  `postgres` service used by `api`/`worker`/dev data.
- Started with `fsync=off`, `synchronous_commit=off`, and
  `full_page_writes=off` (see the `command:` block for the `postgres-test`
  service in `docker-compose.yml`).
- Declared under Compose `profiles: [test]`, so it never starts as part of
  a plain `docker compose up` — it has to be requested explicitly.

**Never use `postgres-test` for anything but disposable local test data.**
`fsync=off` means an unclean shutdown (crash, `docker compose kill`, host
power loss) can corrupt or lose data — acceptable here only because the
test database is recreated from scratch every session (the test suite's
session-scoped fixture runs `alembic upgrade head` before the first test).
Never point `DATABASE_URL`, or any dev/production configuration, at port
5433. The `postgres` service on port 5432 is unaffected by any of this —
its durability settings remain the safe defaults.

### Bring it up

```powershell
docker compose --profile test up -d postgres-test
```

### Point the test suite at it

```powershell
Set-Location backend
$env:DATABASE_URL = 'postgresql+asyncpg://postgres:postgres@localhost:5433/the_creation_os_test'
python -m alembic upgrade head   # first time only, to create the schema on this instance
$env:TEST_DATABASE_URL = 'postgresql+asyncpg://postgres:postgres@localhost:5433/the_creation_os_test'
python -m pytest tests -q
Set-Location ..
```

(The actual Postgres password is whatever is in `secrets/postgres_password.txt`
— `postgres-test` reuses the same `postgres_password` secret as the main
`postgres` service. Substitute it in place of the placeholder above.)

### Bring it down

Stop just this service without touching anything else that's running
(`api`, `postgres`, `redis`, `frontend`, `worker`):

```powershell
docker compose stop postgres-test
```

The stopped container and its data volume are kept, so a later
`docker compose --profile test up -d postgres-test` starts up instantly
with the schema still in place. To also discard the container and its
volume (a full reset — the next `up` recreates it from an empty database
and needs a fresh `alembic upgrade head`):

```powershell
docker compose rm -sf postgres-test
docker volume rm thecreationos_postgres_test_data
```

### Known gotcha: reset it if migration round-trip tests leave it mid-chain

Some integration tests (`test_0013_migration_round_trip_constraints_and_triggers`
and siblings in `test_*_integration.py`) intentionally downgrade the schema
and upgrade back to a specific old revision, not head — that is the point
of those tests. If a test run stops partway (killed, crashed) right after
one of those, the long-lived `postgres-test` container is left sitting on
an old revision instead of head, since it is reused across separate
`pytest` invocations. The next run's session-scoped `alembic upgrade head`
fixture then resumes from that old revision, which can hit a real,
pre-existing ordering bug in `0023_universe_agent_seed` (FK violation)
that only manifests when resuming mid-chain instead of migrating from
empty — this is a real bug in that old migration, not something wrong
with `postgres-test` itself, but `postgres-test`'s persistence between
runs is what exposes it. Confirmed with `SELECT version_num FROM
alembic_version;` — if it doesn't read `0025_god_system_query` (or later)
and `alembic upgrade head` errors out, do the full reset above and try
again; a fresh `postgres-test` migrating from empty always succeeds.
