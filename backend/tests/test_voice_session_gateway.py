from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic.v1 import SecretStr
from starlette.websockets import WebSocketDisconnect

from app.api import voice_session as voice_session_api
from app.api.voice_session import decode_audio_payload
from app.auth.dependencies import get_sovereign_creator
from app.inference.contracts import InferenceRequest, InferenceTimeoutError
from app.main import app
from app.schemas.auth import TokenPayload
from app.voice_session.metrics import VoiceTurnMetrics
from app.voice_session.session import SessionState, VoiceSession, VoiceSessionGateway
from app.voice_session.stt import STTTranscript


class FakeRealtimeSTT:
    def __init__(self, transcripts: list[STTTranscript]) -> None:
        self.transcripts = list(transcripts)
        self.sent: list[tuple[bytes, bool]] = []

    async def send_audio(self, audio: bytes, *, commit: bool = False) -> None:
        self.sent.append((audio, commit))

    async def receive_transcript(self) -> STTTranscript:
        return self.transcripts.pop(0)


class HangingRealtimeSTT:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def send_audio(self, audio: bytes, *, commit: bool = False) -> None:
        return None

    async def receive_transcript(self) -> STTTranscript:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class StubStreamingProvider:
    def __init__(self, name: str, events: list[str | Exception]) -> None:
        self.name = name
        self.events = events
        self.requests: list[InferenceRequest] = []

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        self.requests.append(request)
        for event in self.events:
            if isinstance(event, Exception):
                raise event
            yield event


class FakeRealtimeTTS:
    def __init__(self, audio_events: list[bytes | None]) -> None:
        self.audio_events = list(audio_events)
        self.text: list[str] = []
        self.finished = False

    async def send_text(self, text: str) -> None:
        self.text.append(text)

    async def finish(self) -> None:
        self.finished = True

    async def receive_audio(self) -> bytes | None:
        return self.audio_events.pop(0) if self.audio_events else None



class BufferedRealtimeTTS:
    def __init__(self) -> None:
        self.text: list[str] = []
        self.finished = asyncio.Event()
        self.audio_sent = False

    async def send_text(self, text: str) -> None:
        self.text.append(text)

    async def finish(self) -> None:
        self.finished.set()

    async def receive_audio(self) -> bytes | None:
        await self.finished.wait()
        if self.audio_sent:
            return None
        self.audio_sent = True
        return b"buffered-audio"

def tts_factory(tts: FakeRealtimeTTS):
    @asynccontextmanager
    async def factory():
        yield tts

    return factory


@pytest.fixture
def voice_client(monkeypatch):
    async def fake_creator() -> TokenPayload:
        return TokenPayload(sub="creator-1", type="access", jti="jti", exp=9999999999)

    async def fake_issue_ticket(creator_id: str) -> str:
        assert creator_id == "creator-1"
        return "ticket-1"

    async def fake_consume_ticket(ticket: str) -> str | None:
        return "creator-1" if ticket == "ticket-1" else None

    class FakeDbContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            return None

    class FakeBridge:
        async def validate(self) -> None:
            return None

        async def build_request(self, command: str, turn_id: int) -> InferenceRequest:
            return InferenceRequest(messages=[{"role": "user", "content": command}])

        async def complete_turn(self, turn_id: int, text: str, provider: str) -> None:
            return None

    app.dependency_overrides[get_sovereign_creator] = fake_creator
    monkeypatch.setattr(voice_session_api, "issue_voice_ticket", fake_issue_ticket)
    monkeypatch.setattr(voice_session_api, "consume_voice_ticket", fake_consume_ticket)
    monkeypatch.setattr(voice_session_api, "AsyncSessionLocal", lambda: FakeDbContext())
    monkeypatch.setattr(
        voice_session_api,
        "VoiceConversationBridge",
        lambda *_args, **_kwargs: FakeBridge(),
    )
    monkeypatch.setattr(
        voice_session_api,
        "build_primary_provider",
        lambda: StubStreamingProvider("freellmapi", []),
    )
    monkeypatch.setattr(
        voice_session_api,
        "build_klaus_provider",
        lambda: StubStreamingProvider("klaus", []),
    )
    monkeypatch.setattr(
        voice_session_api,
        "ElevenLabsRealtimeSTT",
        lambda *_args, **_kwargs: HangingRealtimeSTT(),
    )
    monkeypatch.setattr(voice_session_api.settings, "deus_voice_session_enabled", True)
    monkeypatch.setattr(voice_session_api.settings, "elevenlabs_enabled", True)
    monkeypatch.setattr(
        voice_session_api.settings,
        "elevenlabs_api_key",
        SecretStr("test-secret"),
    )

    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_sovereign_creator_can_issue_ephemeral_voice_ticket(voice_client: TestClient):
    response = voice_client.post("/api/v1/voice/session/ticket")

    assert response.status_code == 201
    assert response.json() == {"ticket": "ticket-1"}


def test_websocket_consumes_ticket_and_announces_armed_session(voice_client: TestClient):
    with voice_client.websocket_connect("/api/v1/voice/session?ticket=ticket-1&conversation_id=conversation-1") as websocket:
        ready = websocket.receive_json()

    assert ready["type"] == "session_ready"
    assert ready["state"] == "ARMED"
    assert ready["turn_id"] == 0
    assert ready["creator_id"] == "creator-1"
    assert ready["session_id"]


def test_websocket_rejects_invalid_ticket(voice_client: TestClient):
    with pytest.raises(WebSocketDisconnect) as denied:
        with voice_client.websocket_connect("/api/v1/voice/session?ticket=bad-ticket&conversation_id=conversation-1") as websocket:
            websocket.receive_json()

    assert denied.value.code == 4401


def test_state_machine_exposes_full_realtime_lifecycle():
    assert [state.value for state in SessionState] == [
        "DISCONNECTED",
        "CONNECTING",
        "ARMED",
        "WAKE_DETECTED",
        "LISTENING",
        "COMMITTING",
        "THINKING",
        "SPEAKING",
        "RECOVERING",
        "CLOSED",
    ]


def test_wake_and_command_in_same_committed_transcript_starts_one_turn():
    session = VoiceSession(session_id="session-1")

    decision = session.on_transcript(STTTranscript(text="Deus, verifique o projeto", committed=True))

    assert decision.wake_detected is True
    assert decision.acknowledge is True
    assert decision.command == "verifique o projeto"
    assert decision.turn_id == 1
    assert session.turn_id == 1
    assert session.state is SessionState.COMMITTING


def test_wake_only_enters_continuous_listening_then_followup_commits_without_second_wake():
    session = VoiceSession(session_id="session-1")

    wake = session.on_transcript(STTTranscript(text="Deus", committed=True))
    followup = session.on_transcript(STTTranscript(text="Como está o projeto?", committed=True))

    assert wake.wake_detected is True
    assert wake.command is None
    assert session.turn_id == 1
    assert followup.command == "Como está o projeto?"
    assert followup.turn_id == 1
    assert session.state is SessionState.COMMITTING


def test_duplicate_commit_is_ignored_while_turn_is_in_flight():
    session = VoiceSession(session_id="session-1")
    first = session.on_transcript(STTTranscript(text="Deus, status", committed=True))
    duplicate = session.on_transcript(STTTranscript(text="Deus, status", committed=True))

    assert first.turn_id == 1
    assert duplicate.command is None
    assert session.turn_id == 1


def test_barge_in_cancels_only_the_active_speaking_turn():
    session = VoiceSession(session_id="session-1")
    decision = session.on_transcript(STTTranscript(text="Deus, status", committed=True))

    assert decision.turn_id == 1
    assert session.mark_thinking(1) is True
    assert session.mark_speaking(1) is True
    assert session.state is SessionState.SPEAKING
    assert session.barge_in(0) is False
    assert session.state is SessionState.SPEAKING
    assert session.barge_in(1) is True
    assert session.state is SessionState.LISTENING


def test_metrics_emit_provider_and_stage_latencies_without_content():
    ticks = iter([10.0, 10.1, 10.3, 10.7, 10.9, 11.2, 11.5])
    metrics = VoiceTurnMetrics(session_id="session-1", turn_id=4, clock=lambda: next(ticks))
    metrics.mark("microphone_frame")
    metrics.mark("transcript_committed")
    metrics.mark("llm_started")
    metrics.mark("first_model_token")
    metrics.mark("first_tts_text")
    metrics.mark("first_audio_chunk")
    metrics.mark("completed")
    metrics.provider_selected = "freellmapi"

    payload = metrics.payload()

    assert payload["session_id"] == "session-1"
    assert payload["turn_id"] == 4
    assert payload["provider_selected"] == "freellmapi"
    assert payload["latency_ms"]["transcript_to_first_token"] == 600
    assert payload["latency_ms"]["first_token_to_audio"] == 500
    assert "text" not in payload
    assert "content" not in payload
    assert "audio_base64" not in payload


@pytest.mark.asyncio
async def test_gateway_forwards_pcm_to_realtime_stt():
    stt = FakeRealtimeSTT([])
    tts = FakeRealtimeTTS([None])
    gateway = VoiceSessionGateway(
        session=VoiceSession(session_id="session-1"),
        stt=stt,
        primary=StubStreamingProvider("freellmapi", []),
        fallback=StubStreamingProvider("klaus", []),
        tts_factory=tts_factory(tts),
    )

    await gateway.send_audio(b"\x01\x02", commit=True)

    assert stt.sent == [(b"\x01\x02", True)]


@pytest.mark.asyncio
async def test_gateway_streams_committed_command_through_inference_and_tts_with_one_turn_id():
    stt = FakeRealtimeSTT([
        STTTranscript(text="Deus, verifique o projeto", committed=True),
    ])
    primary = StubStreamingProvider("freellmapi", ["Verificando", "."])
    fallback = StubStreamingProvider("klaus", ["não deve ser usado"])
    tts = FakeRealtimeTTS([b"audio-1", b"audio-2", None])
    gateway = VoiceSessionGateway(
        session=VoiceSession(session_id="session-1"),
        stt=stt,
        primary=primary,
        fallback=fallback,
        tts_factory=tts_factory(tts),
        first_token_timeout_seconds=0.2,
    )

    events: list[dict[str, Any]] = [
        event async for event in gateway.process_next_transcript()
    ]

    assert primary.requests[0].messages == [
        {"role": "user", "content": "verifique o projeto"},
    ]
    assert fallback.requests == []
    assert tts.text == ["Verificando", "."]
    assert tts.finished is True
    assert {event["turn_id"] for event in events if "turn_id" in event} == {1}
    assert [event["type"] for event in events] == [
        "wake_detected",
        "transcript_commit",
        "state",
        "text_delta",
        "audio_chunk",
        "text_delta",
        "audio_chunk",
        "state",
        "telemetry",
    ]
    assert events[2]["state"] == "THINKING"
    assert events[-2]["state"] == "LISTENING"
    assert events[-1]["provider_selected"] == "freellmapi"


@pytest.mark.asyncio
async def test_gateway_speaks_deterministic_service_message_when_both_providers_fail():
    stt = FakeRealtimeSTT([
        STTTranscript(text="Deus, responda", committed=True),
    ])
    primary = StubStreamingProvider(
        "freellmapi",
        [InferenceTimeoutError("freellmapi", "timeout")],
    )
    fallback = StubStreamingProvider(
        "klaus",
        [InferenceTimeoutError("klaus", "timeout")],
    )
    tts = FakeRealtimeTTS([b"service-audio", None])
    gateway = VoiceSessionGateway(
        session=VoiceSession(session_id="session-1"),
        stt=stt,
        primary=primary,
        fallback=fallback,
        tts_factory=tts_factory(tts),
        first_token_timeout_seconds=0.2,
    )

    events = [event async for event in gateway.process_next_transcript()]

    text = "".join(str(event.get("text", "")) for event in events if event["type"] == "text_delta")
    assert "temporariamente indisponível" in text
    assert tts.text == [text]
    assert events[-2]["state"] == "LISTENING"
    assert events[-1]["provider_selected"] == "unavailable"


@pytest.mark.asyncio
async def test_gateway_uses_request_builder_and_completion_callback():
    stt = FakeRealtimeSTT([
        STTTranscript(text="Deus, continue", committed=True),
    ])
    primary = StubStreamingProvider("freellmapi", ["Resposta"])
    fallback = StubStreamingProvider("klaus", [])
    tts = FakeRealtimeTTS([b"audio", None])
    built: list[tuple[str, int]] = []
    completed: list[tuple[int, str, str]] = []

    async def build_request(command: str, turn_id: int) -> InferenceRequest:
        built.append((command, turn_id))
        return InferenceRequest(messages=[
            {"role": "system", "content": "pt-BR"},
            {"role": "user", "content": command},
        ])

    async def on_complete(turn_id: int, text: str, provider: str) -> None:
        completed.append((turn_id, text, provider))

    gateway = VoiceSessionGateway(
        session=VoiceSession(session_id="session-1"),
        stt=stt,
        primary=primary,
        fallback=fallback,
        tts_factory=tts_factory(tts),
        request_builder=build_request,
        on_turn_completed=on_complete,
        first_token_timeout_seconds=0.2,
    )

    events = [event async for event in gateway.process_next_transcript()]

    assert built == [("continue", 1)]
    assert primary.requests[0].messages[0] == {"role": "system", "content": "pt-BR"}
    assert completed == [(1, "Resposta", "freellmapi")]
    assert events[-1]["type"] == "telemetry"


def test_audio_payload_decoder_rejects_malformed_and_oversized_frames():
    from app.voice_session.protocol import ClientEvent

    valid = ClientEvent(
        type="audio",
        session_id="s1",
        turn_id=0,
        audio_base64="AQI=",
        commit=True,
        utterance_id="u-1",
    )
    assert decode_audio_payload(valid) == b"\x01\x02"

    malformed = valid.copy(update={"audio_base64": "***"})
    with pytest.raises(ValueError, match="base64"):
        decode_audio_payload(malformed)

    oversized = valid.copy(
        update={"audio_base64": __import__("base64").b64encode(b"x" * 70000).decode("ascii")}
    )
    with pytest.raises(ValueError, match="too large"):
        decode_audio_payload(oversized)


@pytest.mark.asyncio
async def test_gateway_does_not_block_when_tts_buffers_until_finish():
    stt = FakeRealtimeSTT([
        STTTranscript(text="Deus, diga olá", committed=True),
    ])
    primary = StubStreamingProvider("freellmapi", ["Olá", " mundo."])
    fallback = StubStreamingProvider("klaus", [])
    tts = BufferedRealtimeTTS()
    gateway = VoiceSessionGateway(
        session=VoiceSession(session_id="session-1"),
        stt=stt,
        primary=primary,
        fallback=fallback,
        tts_factory=tts_factory(tts),
        first_token_timeout_seconds=0.2,
    )

    events = await asyncio.wait_for(
        _collect_events(gateway),
        timeout=0.5,
    )

    assert tts.text == ["Olá", " mundo."]
    assert any(event["type"] == "audio_chunk" for event in events)
    assert events[-2]["state"] == "LISTENING"
    assert events[-1]["type"] == "telemetry"


async def _collect_events(gateway: VoiceSessionGateway) -> list[dict[str, object]]:
    return [event async for event in gateway.process_next_transcript()]
