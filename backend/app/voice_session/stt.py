from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode


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
