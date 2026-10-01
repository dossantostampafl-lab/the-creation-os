from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode

from websockets.asyncio.client import connect as websocket_connect


@dataclass(frozen=True)
class ElevenLabsSTTConfig:
    api_key: str
    model_id: str = "scribe_v2_realtime"
    audio_format: str = "pcm_16000"
    language_code: str = "pt"
    commit_strategy: str = "vad"

    @property
    def url(self) -> str:
        query = urlencode(
            {
                "model_id": self.model_id,
                "audio_format": self.audio_format,
                "language_code": self.language_code,
                "commit_strategy": self.commit_strategy,
            }
        )
        return f"wss://api.elevenlabs.io/v1/speech-to-text/realtime?{query}"

    @property
    def headers(self) -> dict[str, str]:
        return {"xi-api-key": self.api_key}


@dataclass(frozen=True)
class STTTranscript:
    text: str
    committed: bool


def encode_audio_chunk(audio: bytes, *, commit: bool = False) -> dict[str, Any]:
    return {
        "message_type": "input_audio_chunk",
        "audio_base_64": base64.b64encode(audio).decode("ascii"),
        "commit": commit,
    }


def parse_stt_event(raw: str) -> STTTranscript | None:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        return None
    message_type = payload.get("message_type")
    text = payload.get("text")
    if not isinstance(text, str):
        return None
    if message_type == "partial_transcript":
        return STTTranscript(text=text, committed=False)
    if message_type == "committed_transcript":
        return STTTranscript(text=text, committed=True)
    return None


class ElevenLabsRealtimeSTT:
    def __init__(
        self,
        config: ElevenLabsSTTConfig,
        *,
        connector: Callable[..., Any] = websocket_connect,
        open_timeout: float = 12.0,
    ) -> None:
        self.config = config
        self._connector = connector
        self._open_timeout = open_timeout
        self._context: Any | None = None
        self._connection: Any | None = None

    async def __aenter__(self) -> "ElevenLabsRealtimeSTT":
        self._context = self._connector(
            self.config.url,
            additional_headers=self.config.headers,
            open_timeout=self._open_timeout,
        )
        self._connection = await self._context.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        context = self._context
        self._context = None
        self._connection = None
        if context is not None:
            await context.__aexit__(exc_type, exc, tb)

    def _require_connection(self) -> Any:
        if self._connection is None:
            raise RuntimeError("ElevenLabs realtime STT is not connected")
        return self._connection

    async def send_audio(self, audio: bytes, *, commit: bool = False) -> None:
        connection = self._require_connection()
        await connection.send(json.dumps(encode_audio_chunk(audio, commit=commit)))

    async def receive_transcript(self) -> STTTranscript:
        connection = self._require_connection()
        while True:
            raw = await connection.recv()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            transcript = parse_stt_event(raw)
            if transcript is not None:
                return transcript
