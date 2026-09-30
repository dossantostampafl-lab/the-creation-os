from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode


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
