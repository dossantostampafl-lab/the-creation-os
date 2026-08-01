from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from db_safety import UnsafeTestDatabaseConfiguration, validated_test_database_url

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-at-least-32-characters")
os.environ.setdefault("CREATOR_BOOTSTRAP_USERNAME", "creator")
os.environ.setdefault("CREATOR_BOOTSTRAP_PASSWORD", "test-password")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture(scope="session", autouse=True)
def _migrate_test_database_to_head():
    """Guarantee the disposable test database starts at Alembic head.

    Without this, a freshly created TEST_DATABASE_URL has no alembic_version
    row, and test_0009_migration_round_trip's `alembic downgrade` has no
    valid current revision to downgrade from — it fails immediately,
    regardless of platform. This mirrors the per-test restore already done
    in pytest_runtest_teardown below, just once, before the session starts.
    """
    try:
        test_database_url = validated_test_database_url()
    except UnsafeTestDatabaseConfiguration:
        return
    environment = os.environ.copy()
    environment["DATABASE_URL"] = test_database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def pytest_runtest_teardown(item, nextitem):
    if "migration_round_trip" not in item.name:
        return
    try:
        test_database_url = validated_test_database_url()
    except UnsafeTestDatabaseConfiguration:
        return

    environment = os.environ.copy()
    environment["DATABASE_URL"] = test_database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
