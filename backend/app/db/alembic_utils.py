from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def resolve_alembic_head() -> str:
    """The Alembic revision the migration scripts on disk currently
    consider "head" — resolved fresh from alembic/versions/ every call,
    not a hardcoded string that has to be remembered and updated by hand
    on every new migration (see ARCHITECTURE.md, Lote: Health check com
    revisão Alembic dinâmica — a hardcoded EXPECTED_ALEMBIC_REVISION in
    app/api/health.py went stale across two prior lotes and left
    /health/ready returning 503 permanently, unnoticed, until a Docker
    rebuild lote's manual verification caught it; the same disease later
    turned up as a second hardcoded head string in a test file, see Lote:
    corrigir revisão stale em test_migration_0023_seed_idempotency.py e
    test_auth.py).

    Resolved relative to the current working directory, deliberately not
    `__file__` — the same convention the `alembic` CLI itself already
    relies on (`alembic.ini` + `alembic/` sit at the process's cwd: the
    repo's `backend/` locally, `/app` in the container's `WORKDIR`). A
    `__file__`-relative path breaks once this module is imported from
    somewhere pip-installed into site-packages rather than run from a
    source checkout, where this module's own location has no fixed
    relationship to where `alembic.ini` lives.

    Not cached: re-scanning alembic/versions/ is cheap (a handful of small
    files), and the alternative — caching per-process — would need its own
    explicit invalidation whenever a migration is added, which is exactly
    the kind of "remember to update this" maintenance burden this function
    exists to eliminate.

    Shared by app/api/health.py (production readiness check) and any test
    that needs to assert against the real current head instead of a
    string that will go stale the next time a migration is added — do not
    duplicate this logic elsewhere.
    """
    config = Config(str(Path.cwd() / "alembic.ini"))
    config.set_main_option("script_location", str(Path.cwd() / "alembic"))
    return ScriptDirectory.from_config(config).get_current_head()
