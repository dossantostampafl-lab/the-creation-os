"""Exercise the deployed nginx config, not a WebSocket mocked in the browser."""
from __future__ import annotations

import asyncio
import shutil
import socket
import subprocess
import uuid
from pathlib import Path

import httpx
import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_frontend_proxy_preserves_voice_websocket_upgrade(tmp_path):
    if shutil.which("docker") is None:
        pytest.skip("requires Docker to exercise production nginx")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]

    async def gateway(websocket):
        assert websocket.request.path == "/api/v1/voice/session?ticket=test-ticket"
        await websocket.send("ARMED")
        assert await websocket.recv() == "microphone frame"
        await websocket.send("frame received")

    async with serve(gateway, "127.0.0.1", 0) as backend:
        upstream_port = backend.sockets[0].getsockname()[1]
        config = (ROOT / "frontend" / "nginx.conf").read_text()
        config = config.replace("listen 8080;", f"listen {port};")
        config = config.replace("http://api:8000", f"http://127.0.0.1:{upstream_port}")
        path = tmp_path / "nginx.conf"
        path.write_text(config)
        name = f"deus-voice-proxy-{uuid.uuid4().hex}"
        try:
            subprocess.run([
                "docker", "run", "--detach", "--rm", "--network", "host", "--name", name,
                "--user", "0", "--volume", f"{path}:/etc/nginx/conf.d/default.conf:ro",
                "nginxinc/nginx-unprivileged:1.27-alpine",
            ], check=True, capture_output=True, timeout=90)
            async with httpx.AsyncClient(timeout=1) as client:
                for attempt in range(50):
                    try:
                        response = await client.get(f"http://127.0.0.1:{port}/healthz")
                        if response.status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    await asyncio.sleep(0.1)
                else:
                    logs = subprocess.run(["docker", "logs", name], capture_output=True, text=True, timeout=10)
                    pytest.fail(f"production nginx did not become healthy: {logs.stdout} {logs.stderr}")
                shell = await client.get(f"http://127.0.0.1:{port}/")
                assert shell.status_code == 200
                assert "no-store" in shell.headers.get("cache-control", "")
                assert "content-security-policy" in shell.headers
            async with connect(
                f"ws://127.0.0.1:{port}/api/v1/voice/session?ticket=test-ticket", open_timeout=5,
            ) as websocket:
                assert await asyncio.wait_for(websocket.recv(), 5) == "ARMED"
                await websocket.send("microphone frame")
                assert await asyncio.wait_for(websocket.recv(), 5) == "frame received"
        finally:
            subprocess.run(["docker", "rm", "--force", name], capture_output=True, timeout=10)
