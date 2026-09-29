"""Runs the real Rust gateway binary so tests cross the Python/Rust boundary for real."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

GATEWAY_DIR = Path(__file__).resolve().parents[2] / "security_gateway"
KEY = "k" * 40
CONTROL_TOKEN = "c" * 40


def _require(message: str) -> None:
    if os.environ.get("STF_REQUIRE_RUST") == "1":
        raise RuntimeError(message)
    pytest.skip(message)


def build_gateway() -> Path:
    if shutil.which("cargo") is None:
        _require("cargo is not installed")
    built = subprocess.run(["cargo", "build", "--locked"], cwd=GATEWAY_DIR, capture_output=True, text=True)
    if built.returncode != 0:
        _require(f"gateway did not build: {built.stderr[-300:]}")
    return GATEWAY_DIR / "target" / "debug" / "creation-security-gateway"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class GatewayProcess:
    def __init__(
        self,
        binary: Path,
        state_dir: Path,
        *,
        port: int | None = None,
        kata: bool = True,
        allowed: str = "cyber_range:",
    ) -> None:
        self.port = port or free_port()
        self._env = {
            **os.environ,
            "STF_GATEWAY_ADDR": f"127.0.0.1:{self.port}",
            "STF_GATEWAY_SIGNING_KEY": KEY,
            "STF_GATEWAY_CONTROL_TOKEN": CONTROL_TOKEN,
            "STF_GATEWAY_STATE_DIR": str(state_dir),
            "STF_ALLOWED_ENVIRONMENTS": allowed,
            "STF_KATA_AVAILABLE": "1" if kata else "0",
            "STF_SANDBOX_BACKEND": "auto",
        }
        self._binary = binary
        self._process: subprocess.Popen | None = None

    def start(self) -> "GatewayProcess":
        self._process = subprocess.Popen(
            [str(self._binary)], env=self._env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.1).close()
                return self
            except OSError:
                time.sleep(0.05)
        self.stop()
        raise RuntimeError("gateway did not start listening")

    def stop(self) -> None:
        if self._process is not None:
            self._process.kill()
            self._process.wait()
            self._process = None
