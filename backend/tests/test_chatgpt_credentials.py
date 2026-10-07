from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.inference.chatgpt_credentials import (
    ChatGPTCredentialRecord,
    ChatGPTCredentialStore,
    _HostFileLock,
)


def _record() -> ChatGPTCredentialRecord:
    return ChatGPTCredentialRecord(
        client_id="oaiapp_test",
        access_token="access-secret",
        refresh_token="refresh-secret",
        scopes=frozenset({"openid", "chatgpt.tokens.use.direct"}),
        saved_at=datetime.now(timezone.utc),
        expires_in=3600,
        id_token="id-secret",
        email="creator@example.com",
        subject="subject-1",
        ext_agent_host_id="urn:uuid:11111111-1111-4111-8111-111111111111",
        earliest_refresh_at=1790033000,
    )


def test_terminal_refresh_cleanup_preserves_registration_but_drops_tokens(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"
    store = ChatGPTCredentialStore(str(path))

    store._clear_unusable_tokens(_record())

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["client_id"] == "oaiapp_test"
    assert payload["subject"] == "subject-1"
    assert payload["ext_agent_host_id"].startswith("urn:uuid:")
    assert payload["plan_usage_enabled"] is False
    assert "access_token" not in payload
    assert "refresh_token" not in payload
    assert "id_token" not in payload


def test_refresh_error_code_uses_machine_readable_oauth_error() -> None:
    import httpx

    response = httpx.Response(
        400,
        request=httpx.Request("POST", "https://auth.openai.com/api/accounts/oauth/token"),
        json={"error": "refresh_token_reused"},
    )

    assert ChatGPTCredentialStore._response_error_code(response) == "refresh_token_reused"


def test_refresh_write_preserves_production_issuer_and_plan_marker(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"
    store = ChatGPTCredentialStore(str(path))
    previous = _record()

    stored = store._write(
        previous,
        {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
            "scope": "openid chatgpt.tokens.use.direct",
        },
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["issuer"] == "https://auth.openai.com"
    assert payload["plan_usage_enabled"] is True
    assert stored.access_token == "new-access"


_HOLD_LOCK = """
import fcntl, os, sys
fd = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX)
print("locked", flush=True)
sys.stdin.readline()
"""

_TRY_LOCK = """
import fcntl, os, sys, time
fd = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR, 0o600)
deadline = time.monotonic() + 5
while True:
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sys.exit(0)
    except BlockingIOError:
        if time.monotonic() > deadline:
            sys.exit(1)
        time.sleep(0.02)
"""


def _open_fds_for(path: Path) -> int:
    fd_dir = Path("/proc/self/fd")
    count = 0
    for entry in fd_dir.iterdir():
        try:
            if Path(os.readlink(entry)) == path:
                count += 1
        except OSError:
            continue
    return count


@pytest.mark.skipif(not Path("/proc/self/fd").is_dir(), reason="needs /proc to inspect open descriptors")
async def test_cancelled_lock_wait_releases_the_host_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "credentials.json.lock"
    holder = subprocess.Popen(
        [sys.executable, "-c", _HOLD_LOCK, str(lock_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None and holder.stdout.readline().strip() == "locked"

        async def acquire() -> None:
            async with _HostFileLock(lock_path):
                pytest.fail("the lock must stay held by the other process")

        waiter = asyncio.create_task(acquire())
        await asyncio.sleep(0.2)
        assert not waiter.done()
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert _open_fds_for(lock_path) == 0

        assert holder.stdin is not None
        holder.stdin.write("release\n")
        holder.stdin.flush()
        assert holder.wait(timeout=5) == 0

        # Give a leaked waiter (the old blocking-thread implementation) time to grab the lock.
        await asyncio.sleep(0.3)
        third = subprocess.run(
            [sys.executable, "-c", _TRY_LOCK, str(lock_path)],
            timeout=10,
        )
        assert third.returncode == 0, "a third process must still acquire the lock"
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait()


async def test_host_lock_is_released_after_use(tmp_path: Path) -> None:
    lock_path = tmp_path / "credentials.json.lock"
    async with _HostFileLock(lock_path):
        pass
    result = subprocess.run([sys.executable, "-c", _TRY_LOCK, str(lock_path)], timeout=10)
    assert result.returncode == 0
