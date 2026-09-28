from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol


class GatewayUnavailable(RuntimeError):
    """The gateway could not be reached; privileged execution stays off."""


class GatewayClient(Protocol):
    async def execute(self, envelope: dict[str, Any], requested: dict[str, Any]) -> dict[str, Any]: ...

    async def control(self, message: dict[str, Any]) -> dict[str, Any]: ...


class TcpGatewayClient:
    """Line-delimited JSON to the Rust gateway over the internal stf-control network."""

    def __init__(self, host: str = "stf-gateway", port: int = 7443, *, timeout: float = 5.0) -> None:
        self._host, self._port, self._timeout = host, port, timeout

    async def _send(self, message: dict[str, Any]) -> dict[str, Any]:
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(self._host, self._port), self._timeout)
            writer.write(json.dumps(message, sort_keys=True).encode() + b"\n")
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), self._timeout)
            writer.close()
            return json.loads(line)
        except (OSError, TimeoutError, ValueError) as error:
            raise GatewayUnavailable(error.__class__.__name__) from error

    async def execute(self, envelope: dict[str, Any], requested: dict[str, Any]) -> dict[str, Any]:
        return await self._send({"op": "execute", "envelope": envelope, "requested": requested})

    async def control(self, message: dict[str, Any]) -> dict[str, Any]:
        return await self._send(message)
