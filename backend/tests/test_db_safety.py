from __future__ import annotations

import pytest
from db_safety import (
    UnsafeTestDatabaseConfiguration,
    create_isolated_test_engine,
    validate_test_database_url,
    validated_test_database_url,
)

VALID = "postgresql+asyncpg://tester:secret@localhost/the_creation_os_test"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_test_database_url_is_required(value):
    with pytest.raises(UnsafeTestDatabaseConfiguration, match="TEST_DATABASE_URL is required"):
        validate_test_database_url(value)


@pytest.mark.parametrize(
    "value, message",
    [
        ("not a URL", "malformed"),
        ("mysql://tester:secret@localhost/project_test", "must use postgresql\\+asyncpg"),
        ("postgresql+asyncpg://tester:secret@localhost", "must identify a database"),
        ("postgresql+asyncpg:///project_test", "must identify a hostname"),
    ],
)
def test_malformed_or_incompatible_urls_are_rejected(value, message):
    with pytest.raises(UnsafeTestDatabaseConfiguration, match=message):
        validate_test_database_url(value)


@pytest.mark.parametrize(
    "database", ["the_creation_os", "THE_CREATION_OS", '"the_creation_os"', "postgres", "template0", "template1"]
)
def test_protected_databases_are_rejected_case_insensitively(database):
    with pytest.raises(UnsafeTestDatabaseConfiguration, match="protected"):
        validate_test_database_url(f"postgresql+asyncpg://tester:secret@localhost/{database}")


@pytest.mark.parametrize("database", ["the_creation_os_dev", "the_creation_os_local", "creation", "contest"])
def test_database_name_requires_positive_test_identification(database):
    with pytest.raises(UnsafeTestDatabaseConfiguration, match="explicitly identify"):
        validate_test_database_url(f"postgresql+asyncpg://tester:secret@localhost/{database}")


@pytest.mark.parametrize(
    "database",
    ["the_creation_os_test", "the_creation_os_v046_test", "test_the_creation_os", "the_creation_os_integration_tests"],
)
def test_explicit_test_database_names_are_accepted(database):
    result = validate_test_database_url(f"postgresql+asyncpg://tester:secret@localhost/{database}")
    assert result.endswith(f"/{database}")


def test_same_application_url_is_rejected():
    with pytest.raises(UnsafeTestDatabaseConfiguration, match="application database"):
        validate_test_database_url(VALID, VALID)


def test_same_logical_database_with_different_credentials_is_rejected():
    application = "postgresql+asyncpg://application:other@LOCALHOST:5432/the_creation_os_test"
    with pytest.raises(UnsafeTestDatabaseConfiguration, match="application database"):
        validate_test_database_url(VALID, application)


def test_default_and_explicit_postgresql_ports_are_equivalent():
    application = "postgresql+asyncpg://application:other@localhost:5432/the_creation_os_test"
    with pytest.raises(UnsafeTestDatabaseConfiguration, match="application database"):
        validate_test_database_url(VALID, application)


def test_different_test_database_on_same_server_is_accepted():
    application = "postgresql+asyncpg://application:other@localhost:5432/the_creation_os"
    assert validate_test_database_url(VALID, application).endswith("/the_creation_os_test")


def test_asyncpg_url_with_explicit_port_is_accepted():
    value = "postgresql+asyncpg://tester:secret@db.example:5544/test_the_creation_os"
    assert validate_test_database_url(value) == value


def test_connection_routing_query_parameters_are_rejected():
    value = "postgresql+asyncpg://tester:secret@localhost/project_test?host=other-host"
    with pytest.raises(UnsafeTestDatabaseConfiguration, match="must not override connection routing"):
        validate_test_database_url(value)


def test_errors_never_expose_passwords():
    password = "do-not-leak-this-password"
    unsafe = f"postgresql+asyncpg://tester:{password}@localhost/the_creation_os"
    with pytest.raises(UnsafeTestDatabaseConfiguration) as captured:
        validate_test_database_url(unsafe)
    assert password not in str(captured.value)


def test_environment_lookup_requires_test_database_url():
    with pytest.raises(UnsafeTestDatabaseConfiguration, match="TEST_DATABASE_URL is required"):
        validated_test_database_url({})


def test_unsafe_configuration_fails_before_engine_or_sql_is_reachable():
    calls = []

    def forbidden_engine_factory(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("engine creation must not be reached")

    with pytest.raises(UnsafeTestDatabaseConfiguration, match="protected"):
        create_isolated_test_engine(
            {"TEST_DATABASE_URL": "postgresql+asyncpg://tester:secret@localhost/the_creation_os"},
            engine_factory=forbidden_engine_factory,
        )
    assert calls == []


def test_valid_configuration_reaches_engine_only_with_validated_url():
    calls = []

    def engine_factory(url):
        calls.append(url)
        return "engine"

    result = create_isolated_test_engine(
        {"TEST_DATABASE_URL": VALID},
        engine_factory=engine_factory,
    )
    assert result == "engine"
    assert calls == [VALID]
