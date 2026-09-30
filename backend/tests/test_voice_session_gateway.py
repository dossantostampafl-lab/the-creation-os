from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import voice_session as voice_session_api
from app.auth.dependencies import get_sovereign_creator
from app.main import app
from app.schemas.auth import TokenPayload
from app.voice_session.session import SessionState, VoiceSession
from app.voice_session.stt import STTTranscript


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
