from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from stf_database import guarded_test_database_url

from app.db.session import create_session_engine


@pytest.mark.integration
async def test_application_pool_replaces_a_closed_idle_connection():
    # Only terminate our own idle connection in the guarded disposable database.
    url = guarded_test_database_url()
    engine = create_session_engine(url)
    admin = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            stale_pid = await connection.scalar(text("SELECT pg_backend_pid()"))
        async with admin.begin() as connection:
            assert await connection.scalar(text("SELECT pg_terminate_backend(:pid, 5000)"), {"pid": stale_pid})
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT pg_backend_pid()")) != stale_pid
            assert await connection.scalar(text("SELECT 1")) == 1
    finally:
        await engine.dispose()
        await admin.dispose()
