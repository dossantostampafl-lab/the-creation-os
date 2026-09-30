from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import voice_session as voice_session_api
from app.auth.dependencies import get_sovereign_creator
from app.inference.contracts import InferenceRequest
from app.main import app
from app.schemas.auth import TokenPayload
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


class StubStreamingProvider:
    def __init__(self, name: str, chunks: list[str]) -> None:
        self.name = name
        self.chunks = chunks
        self.requests: list[InferenceRequest] = []

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        self.requests.append(request)
        for chunk in self.chunks:
            yield chunk


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
        return self.audio_events.pop(0)


@pytest.fixture
def voice_client(monkeypatch):
    async def fake_creator() -> TokenPayload:
        return TokenPayload(sub="creator-1", type="access", jti="jti", exp=9999999999)

    async def fake_issue_ticket(creator_id: str) -> str:
        assert creator_id == "creator-1"
        return "ticket-1"

    async def fake_consume_ticket(ticket: str) -> str | None:
        return "creator-1" if ticket == "ticket-1" else None

    app.dependency_overrides[get_sovereign_creator] = fake_creator
    monkeypatch.setattr(voice_session_api, "issue_voice_ticket", fake_issue_ticket)
    monkeypatch.setattr(voice_session_api, "consume_voice_ticket", fake_consume_ticket)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_sovereign_creator_can_issue_ephemeral_voice_ticket(voice_client: TestClient):
    response = voice_client.post("/api/v1/voice/session/ticket")

    assert response.status_code == 201
    assert response.json() == {"ticket": "ticket-1"}


def test_websocket_consumes_ticket_and_announces_armed_session(voice_client: TestClient):
    with voice_client.websocket_connect("/api/v1/voice/session?ticket=ticket-1") as websocket:
        ready = websocket.receive_json()

    assert ready["type"] == "session_ready"
    assert ready["state"] == "ARMED"
    assert ready["turn_id"] == 0
    assert ready["creator_id"] == "creator-1"
    assert ready["session_id"]


def test_websocket_rejects_invalid_ticket(voice_client: TestClient):
    with pytest.raises(WebSocketDisconnect) as denied:
        with voice_client.websocket_connect("/api/v1/voice/session?ticket=bad-ticket") as websocket:
            websocket.receive_json()

    assert denied.value.code == 4401


def test_wake_and_command_in_same_committed_transcript_starts_one_turn():
    session = VoiceSession(session_id="session-1")

    decision = session.on_transcript(STTTranscript(text="Deus, verifique o projeto", committed=True))

    assert decision.wake_detected is True
    assert decision.acknowledge is True
    assert decision.command == "verifique o projeto"
    assert decision.turn_id == 1
    assert session.turn_id == 1
    assert session.state is SessionState.THINKING


def test_wake_only_enters_continuous_listening_then_followup_commits_without_second_wake():
    session = VoiceSession(session_id="session-1")

    wake = session.on_transcript(STTTranscript(text="Deus", committed=True))
    followup = session.on_transcript(STTTranscript(text="Como está o projeto?", committed=True))

    assert wake.wake_detected is True
    assert wake.command is None
    assert session.turn_id == 1
    assert followup.command == "Como está o projeto?"
    assert followup.turn_id == 1
    assert session.state is SessionState.THINKING


def test_barge_in_cancels_only_the_active_speaking_turn():
    session = VoiceSession(session_id="session-1")
    decision = session.on_transcript(STTTranscript(text="Deus, status", committed=True))

    assert decision.turn_id == 1
    assert session.mark_speaking(1) is True
    assert session.state is SessionState.SPEAKING
    assert session.barge_in(0) is False
    assert session.state is SessionState.SPEAKING
    assert session.barge_in(1) is True
    assert session.state is SessionState.LISTENING


@pytest.mark.asyncio
async def test_gateway_forwards_pcm_to_realtime_stt():
    stt = FakeRealtimeSTT([])
    gateway = VoiceSessionGateway(
        session=VoiceSession(session_id="session-1"),
        stt=stt,
        primary=StubStreamingProvider("freellmapi", []),
        fallback=StubStreamingProvider("klaus", []),
        tts=FakeRealtimeTTS([None]),
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
        tts=tts,
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
        "state",
        "text_delta",
        "audio_chunk",
        "text_delta",
        "audio_chunk",
        "state",
    ]
    assert events[1]["state"] == "THINKING"
    assert events[-1]["state"] == "LISTENING"
