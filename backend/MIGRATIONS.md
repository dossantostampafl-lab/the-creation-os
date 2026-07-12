# Migration compatibility note

`0001_initial` had not been applied to the persistent local Docker database when
the v0.3 stabilization began (`alembic current` returned no revision).

Two source defects were corrected before its first verified application:

- invalid Python syntax `psql.REAL[]()` was changed to `psql.ARRAY(psql.REAL())`;
- unused `CREATE/DROP EXTENSION vector` statements were removed because the
  schema stores embeddings as PostgreSQL `REAL[]`, not `vector`.

The resulting table type remains `REAL[]`. An external database that previously
ran a manually repaired copy of `0001` may retain an unused `vector` extension;
that does not change the application schema and must not be removed automatically.
