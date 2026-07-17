from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from db_safety import UnsafeTestDatabaseConfiguration, validated_test_database_url

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-at-least-32-characters")
os.environ.setdefault("CREATOR_BOOTSTRAP_USERNAME", "creator")
os.environ.setdefault("CREATOR_BOOTSTRAP_PASSWORD", "test-password")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


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
