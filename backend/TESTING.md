# Test database safety

Unit tests do not require `TEST_DATABASE_URL`:

```powershell
pytest -m "not integration"
```

PostgreSQL integration tests are destructive. Their fixtures truncate all data
in the configured test database. The operator must deliberately create a
disposable database whose name clearly identifies it as a test database, then
set its complete URL explicitly:

```powershell
$env:TEST_DATABASE_URL='postgresql+asyncpg://postgres:<test-password>@localhost:5432/the_creation_os_v046_test'
pytest -m integration
```

Safety rules:

- never use `the_creation_os` as the test database;
- never set `TEST_DATABASE_URL` to the same logical database as `DATABASE_URL`;
- do not use a development or local database unless it is disposable and its
  name explicitly contains a test marker;
- create the test database deliberately before running integration tests;
- expect integration fixtures to erase every record in that disposable database.

The test harness rejects missing, malformed, non-PostgreSQL, production-like,
or application-equivalent URLs before it creates the integration-test engine.
It does not fall back to `DATABASE_URL`.
