from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote, urlencode

from websockets.asyncio.client import connect as websocket_connect


@dataclass(frozen=True)
class ElevenLabsTTSConfig:
    api_key: str
    voice_id: str
    model_id: str = "eleven_flash_v2_5"
    language_code: str = "pt"
    output_format: str = "mp3_22050_32"

    @property
    def url(self) -> str:
        voice = quote(self.voice_id, safe="")
        query = urlencode(
            {
                "model_id": self.model_id,
                "language_code": self.language_code,
                "output_format": self.output_format,
            }
        )
        return f"wss://api.elevenlabs.io/v1/text-to-speech/{voice}/stream-input?{query}"

    @property
    def headers(self) -> dict[str, str]:
        return {"xi-api-key": self.api_key}


def encode_tts_initialize() -> dict[str, Any]:
    return {"text": " "}


def encode_tts_text(text: str) -> dict[str, Any]:
    return {"text": text}


def encode_tts_close() -> dict[str, Any]:
    return {"text": ""}


def parse_tts_event(raw: str) -> bytes | None:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        return None
    audio = payload.get("audio")
    if isinstance(audio, str) and audio:
        return base64.b64decode(audio)
    return None


class ElevenLabsRealtimeTTS:
    def __init__(
        self,
        config: ElevenLabsTTSConfig,
        *,
        connector: Callable[..., Any] = websocket_connect,
        open_timeout: float = 12.0,
    ) -> None:
        self.config = config
        self._connector = connector
        self._open_timeout = open_timeout
        self._context: Any | None = None
        self._connection: Any | None = None

    async def __aenter__(self) -> "ElevenLabsRealtimeTTS":
        self._context = self._connector(
            self.config.url,
            additional_headers=self.config.headers,
            open_timeout=self._open_timeout,
        )
        self._connection = await self._context.__aenter__()
        await self._connection.send(json.dumps(encode_tts_initialize()))
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        context = self._context
        self._context = None
        self._connection = None
        if context is not None:
            await context.__aexit__(exc_type, exc, tb)

    def _require_connection(self) -> Any:
        if self._connection is None:
            raise RuntimeError("ElevenLabs realtime TTS is not connected")
        return self._connection

    async def send_text(self, text: str) -> None:
        connection = self._require_connection()
        await connection.send(json.dumps(encode_tts_text(text)))

    async def finish(self) -> None:
        connection = self._require_connection()
        await connection.send(json.dumps(encode_tts_close()))

    async def receive_audio(self) -> bytes | None:
        connection = self._require_connection()
        raw = await connection.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return parse_tts_event(raw)
