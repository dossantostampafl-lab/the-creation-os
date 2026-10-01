from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from app.voice_session.stt import ElevenLabsRealtimeSTT, ElevenLabsSTTConfig, STTTranscript
from app.voice_session.tts import ElevenLabsRealtimeTTS, ElevenLabsTTSConfig


class FakeConnection:
    def __init__(self, incoming: list[str]) -> None:
        self.incoming = list(incoming)
        self.sent: list[str] = []

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    async def recv(self) -> str:
        return self.incoming.pop(0)


class FakeConnectionContext:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, *_args: Any) -> None:
        return None


class FakeConnector:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, url: str, **kwargs: Any) -> FakeConnectionContext:
        self.calls.append((url, kwargs))
        return FakeConnectionContext(self.connection)


@pytest.mark.asyncio
async def test_realtime_stt_connects_with_backend_key_and_streams_pcm():
    connection = FakeConnection([
        '{"message_type":"partial_transcript","text":"Deus"}',
    ])
    connector = FakeConnector(connection)
    config = ElevenLabsSTTConfig(api_key="secret")

    async with ElevenLabsRealtimeSTT(config, connector=connector) as stt:
        await stt.send_audio(b"\x01\x02", commit=True)
        transcript = await stt.receive_transcript()

    assert transcript == STTTranscript(text="Deus", committed=False)
    assert connector.calls == [
        (
            config.url,
            {
                "additional_headers": {"xi-api-key": "secret"},
                "open_timeout": 12.0,
            },
        )
    ]
    sent = json.loads(connection.sent[0])
    assert sent["message_type"] == "input_audio_chunk"
    assert sent["audio_base_64"] == base64.b64encode(b"\x01\x02").decode("ascii")
    assert sent["commit"] is True


@pytest.mark.asyncio
async def test_realtime_tts_initializes_streams_text_and_returns_audio():
    encoded = base64.b64encode(b"audio").decode("ascii")
    connection = FakeConnection([
        '{"alignment":{"chars":["O"]},"is_final":false}',
        '{"audio":"' + encoded + '","is_final":false}',
    ])
    connector = FakeConnector(connection)
    config = ElevenLabsTTSConfig(
        api_key="secret",
        voice_id="voice-1",
        model_id="eleven_flash_v2_5",
    )

    async with ElevenLabsRealtimeTTS(config, connector=connector) as tts:
        await tts.send_text("Olá ")
        await tts.finish()
        audio = await tts.receive_audio()

    assert audio == b"audio"
    assert connector.calls == [
        (
            config.url,
            {
                "additional_headers": {"xi-api-key": "secret"},
                "open_timeout": 12.0,
            },
        )
    ]
    assert [json.loads(payload) for payload in connection.sent] == [
        {"text": " "},
        {"text": "Olá ", "try_trigger_generation": True},
        {"text": ""},
    ]


@pytest.mark.asyncio
async def test_realtime_tts_returns_none_only_for_final_event():
    connection = FakeConnection([
        '{"alignment":{"chars":["O"]},"is_final":false}',
        '{"is_final":true}',
    ])
    connector = FakeConnector(connection)
    config = ElevenLabsTTSConfig(api_key="secret", voice_id="voice-1")

    async with ElevenLabsRealtimeTTS(config, connector=connector) as tts:
        assert await tts.receive_audio() is None
