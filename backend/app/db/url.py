def normalize_database_url(value: str) -> str:
    """Return a SQLAlchemy asyncpg URL for managed PostgreSQL connection strings."""
    if value.startswith("postgresql://"):
        return "postgresql+asyncpg://" + value.removeprefix("postgresql://")
    if value.startswith("postgres://"):
        return "postgresql+asyncpg://" + value.removeprefix("postgres://")
    return value
