from app.db.url import normalize_database_url


def test_normalizes_database_postgres_scheme() -> None:
    assert normalize_database_url("postgresql://u:p@host/db") == "postgresql+asyncpg://u:p@host/db"


def test_normalizes_legacy_postgres_scheme() -> None:
    assert normalize_database_url("postgres://u:p@host/db") == "postgresql+asyncpg://u:p@host/db"


def test_preserves_explicit_asyncpg_scheme() -> None:
    value = "postgresql+asyncpg://u:p@host/db"
    assert normalize_database_url(value) == value
