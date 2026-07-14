from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import create_async_engine


class UnsafeTestDatabaseConfiguration(RuntimeError):
    """Raised before any database engine is created for an unsafe test URL."""


FORBIDDEN_DATABASES = frozenset({"the_creation_os", "postgres", "template0", "template1"})
TEST_DATABASE_PATTERN = re.compile(r"(?:^test(?:_|$)|(?:^|_)tests?(?:_|$)|(?:^|_)testing(?:_|$))", re.IGNORECASE)
PROJECT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def _parse_postgresql_url(raw_url: str, *, label: str) -> URL:
    try:
        parsed = make_url(raw_url)
    except (ArgumentError, TypeError, ValueError) as exc:
        raise UnsafeTestDatabaseConfiguration(f"Unsafe integration-test configuration: {label} is malformed.") from exc
    if parsed.drivername != "postgresql+asyncpg":
        raise UnsafeTestDatabaseConfiguration(
            f"Unsafe integration-test configuration: {label} must use postgresql+asyncpg."
        )
    if parsed.query:
        raise UnsafeTestDatabaseConfiguration(
            f"Unsafe integration-test configuration: {label} must not override connection routing."
        )
    return parsed


def _normalized_database_name(parsed: URL, *, label: str) -> str:
    if not parsed.database:
        raise UnsafeTestDatabaseConfiguration(
            f"Unsafe integration-test configuration: {label} must identify a database."
        )
    normalized = parsed.database.strip().strip("\"'").casefold()
    if not normalized:
        raise UnsafeTestDatabaseConfiguration(
            f"Unsafe integration-test configuration: {label} must identify a database."
        )
    return normalized


def _database_identity(parsed: URL, *, label: str) -> tuple[str, int, str]:
    if not parsed.host:
        raise UnsafeTestDatabaseConfiguration(
            f"Unsafe integration-test configuration: {label} must identify a hostname."
        )
    return parsed.host.casefold(), parsed.port or 5432, _normalized_database_name(parsed, label=label)


def validate_test_database_url(
    test_database_url: str | None,
    application_database_url: str | None = None,
) -> str:
    """Return a connection URL only after conservative, credential-safe validation."""
    if test_database_url is None or not test_database_url.strip():
        raise UnsafeTestDatabaseConfiguration(
            "Unsafe integration-test configuration: TEST_DATABASE_URL is required."
        )

    parsed_test = _parse_postgresql_url(test_database_url.strip(), label="TEST_DATABASE_URL")
    test_identity = _database_identity(parsed_test, label="TEST_DATABASE_URL")
    test_database = test_identity[2]
    if test_database in FORBIDDEN_DATABASES:
        raise UnsafeTestDatabaseConfiguration(
            f"Unsafe integration-test configuration: database '{test_database}' is protected."
        )
    if TEST_DATABASE_PATTERN.search(test_database) is None:
        raise UnsafeTestDatabaseConfiguration(
            "Unsafe integration-test configuration: the database name must explicitly identify a test database."
        )

    if application_database_url and application_database_url.strip():
        parsed_application = _parse_postgresql_url(application_database_url.strip(), label="DATABASE_URL")
        application_identity = _database_identity(parsed_application, label="DATABASE_URL")
        if test_identity == application_identity:
            raise UnsafeTestDatabaseConfiguration(
                "Unsafe integration-test configuration: TEST_DATABASE_URL targets the application database."
            )

    return parsed_test.render_as_string(hide_password=False)


def configured_application_database_url(environ: Mapping[str, str]) -> str | None:
    """Read the application URL without opening a connection or exposing credentials."""
    configured = environ.get("DATABASE_URL")
    if configured:
        return configured
    if PROJECT_ENV_FILE.is_file():
        value = dotenv_values(PROJECT_ENV_FILE).get("DATABASE_URL")
        return str(value) if value else None
    return None


def validated_test_database_url(environ: Mapping[str, str] | None = None) -> str:
    environment = os.environ if environ is None else environ
    return validate_test_database_url(
        environment.get("TEST_DATABASE_URL"),
        configured_application_database_url(environment),
    )


def create_isolated_test_engine(
    environ: Mapping[str, str] | None = None,
    *,
    engine_factory: Callable[..., Any] = create_async_engine,
):
    """Validate first, then and only then construct the integration-test engine."""
    return engine_factory(validated_test_database_url(environ))
