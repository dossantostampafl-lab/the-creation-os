from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.api.voice import service as voice_service_dependency
from app.auth.dependencies import get_sovereign_creator
from app.core.domain import Actor
from app.main import app
from app.schemas.auth import TokenPayload
from app.services.voice import (
    VOICE_PROVIDER_UNAVAILABLE,
    VOICE_SYNTHESIS_DISABLED,
    VOICE_SYNTHESIS_EMPTY_TEXT,
    VOICE_TRANSCRIPTION_DISABLED,
    VOICE_TRANSCRIPTION_EMPTY_AUDIO,
    VOICE_TRANSCRIPTION_TOO_LARGE,
    VOICE_TRANSCRIPTION_UNAVAILABLE,
    VoiceSynthesisService,
)


class FakeVoiceRepository:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self.commits = 0

    async def add_event(self, event_type, aggregate_type, aggregate_id, actor_id, actor_role, correlation_id, payload=None):
        self.events.append((event_type, payload or {}))

    async def commit(self):
        self.commits += 1


class FakeVoiceService:
    async def synthesize(self, actor: Actor, text: str, correlation_id: str):
        assert actor.role == "creator"
        assert text == "DEUS presente"
        assert correlation_id
        return b"audio-bytes", "audio/mpeg"

    async def transcribe(self, actor: Actor, audio: bytes, content_type: str, correlation_id: str):
        assert actor.role == "creator"
        assert audio == b"voice-bytes"
        assert content_type == "audio/webm"
        assert correlation_id
        return "Deus, status dos universos", "por", 0.98


@pytest.mark.asyncio
async def test_voice_synthesis_rejects_empty_text():
    service = VoiceSynthesisService(FakeVoiceRepository())  # type: ignore[arg-type]
    with pytest.raises(VOICE_SYNTHESIS_EMPTY_TEXT):
        await service.synthesize(Actor("creator-1", "creator"), "   ", "c")


@pytest.mark.asyncio
async def test_voice_synthesis_disabled_is_controlled(monkeypatch):
    monkeypatch.setattr("app.services.voice.settings.elevenlabs_enabled", False)
    service = VoiceSynthesisService(FakeVoiceRepository())  # type: ignore[arg-type]
    with pytest.raises(VOICE_SYNTHESIS_DISABLED):
        await service.synthesize(Actor("creator-1", "creator"), "DEUS presente", "c")


@pytest.mark.asyncio
async def test_voice_synthesis_calls_elevenlabs_without_auditing_secret(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["xi-api-key"] == "secret-key"
        assert request.headers["accept"] == "audio/mpeg"
        assert request.url.path == "/v1/text-to-speech/voice-1"
        return httpx.Response(200, content=b"audio", headers={"content-type": "audio/mpeg"})

    monkeypatch.setattr("app.services.voice.settings.elevenlabs_enabled", True)
    monkeypatch.setattr("app.services.voice.settings.elevenlabs_api_key", SecretStr("secret-key"))
    monkeypatch.setattr("app.services.voice.settings.elevenlabs_voice_id", "voice-1")
    repository = FakeVoiceRepository()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = VoiceSynthesisService(repository, client=client)  # type: ignore[arg-type]

    audio, content_type = await service.synthesize(Actor("creator-1", "creator"), "DEUS presente", "c")

    await client.aclose()
    assert audio == b"audio"
    assert content_type == "audio/mpeg"
    assert [event[0] for event in repository.events] == ["voice.synthesis.requested", "voice.synthesis.succeeded"]
    assert "secret-key" not in str(repository.events)


@pytest.mark.asyncio
async def test_voice_synthesis_provider_error_is_controlled(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"detail": "rate limited"})

    monkeypatch.setattr("app.services.voice.settings.elevenlabs_enabled", True)
    monkeypatch.setattr("app.services.voice.settings.elevenlabs_api_key", SecretStr("secret-key"))
    repository = FakeVoiceRepository()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = VoiceSynthesisService(repository, client=client)  # type: ignore[arg-type]

    with pytest.raises(VOICE_PROVIDER_UNAVAILABLE):
        await service.synthesize(Actor("creator-1", "creator"), "DEUS presente", "c")

    await client.aclose()
    assert repository.events[-1][0] == "voice.synthesis.failed"


@pytest.mark.asyncio
async def test_voice_synthesize_endpoint_returns_audio():
    async def fake_creator():
        return TokenPayload(sub="creator-1", type="access", jti="jti", exp=9999999999)

    app.dependency_overrides[get_sovereign_creator] = fake_creator
    app.dependency_overrides[voice_service_dependency] = lambda: FakeVoiceService()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/voice/synthesize",
                headers={"Authorization": "Bearer test-token"},
                json={"text": "DEUS presente"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"audio-bytes"
    assert response.headers["content-type"] == "audio/mpeg"


@pytest.mark.asyncio
async def test_voice_synthesis_commits_before_calling_the_provider(monkeypatch):
    repository = FakeVoiceRepository()

    async def handler(request: httpx.Request) -> httpx.Response:
        # The requested event must already be committed so the Chronicle lock is released.
        assert repository.commits == 1
        return httpx.Response(200, content=b"audio", headers={"content-type": "audio/mpeg"})

    monkeypatch.setattr("app.services.voice.settings.elevenlabs_enabled", True)
    monkeypatch.setattr("app.services.voice.settings.elevenlabs_api_key", SecretStr("secret-key"))
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = VoiceSynthesisService(repository, client=client)  # type: ignore[arg-type]

    await service.synthesize(Actor("creator-1", "creator"), "DEUS presente", "c")

    await client.aclose()
    assert repository.commits == 2


class RaisingVoiceService:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def synthesize(self, actor: Actor, text: str, correlation_id: str):
        raise self.error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status"),
    [
        (VOICE_SYNTHESIS_DISABLED("disabled"), 501),
        (VOICE_SYNTHESIS_EMPTY_TEXT("empty"), 422),
        (VOICE_PROVIDER_UNAVAILABLE("down"), 503),
    ],
)
async def test_voice_synthesize_endpoint_maps_failures_to_http_status(error, status):
    async def fake_creator():
        return TokenPayload(sub="creator-1", type="access", jti="jti", exp=9999999999)

    app.dependency_overrides[get_sovereign_creator] = fake_creator
    app.dependency_overrides[voice_service_dependency] = lambda: RaisingVoiceService(error)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/voice/synthesize", json={"text": "DEUS presente"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == status


@pytest.mark.asyncio
async def test_voice_transcription_rejects_empty_audio():
    service = VoiceSynthesisService(FakeVoiceRepository())  # type: ignore[arg-type]
    with pytest.raises(VOICE_TRANSCRIPTION_EMPTY_AUDIO):
        await service.transcribe(Actor("creator-1", "creator"), b"", "audio/webm", "c")


@pytest.mark.asyncio
async def test_voice_transcription_calls_scribe_in_portuguese(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["xi-api-key"] == "secret-key"
        assert request.url.path == "/v1/speech-to-text"
        body = request.content
        assert b"scribe_v2" in body
        assert b"por" in body
        assert b"voice-bytes" in body
        return httpx.Response(
            200,
            json={
                "text": "Deus, status dos universos",
                "language_code": "por",
                "language_probability": 0.98,
            },
        )

    monkeypatch.setattr("app.services.voice.settings.elevenlabs_enabled", True)
    monkeypatch.setattr("app.services.voice.settings.elevenlabs_api_key", SecretStr("secret-key"))
    monkeypatch.setattr("app.services.voice.settings.elevenlabs_stt_model_id", "scribe_v2")
    repository = FakeVoiceRepository()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = VoiceSynthesisService(repository, client=client)  # type: ignore[arg-type]

    text, language_code, probability = await service.transcribe(
        Actor("creator-1", "creator"), b"voice-bytes", "audio/webm", "c"
    )

    await client.aclose()
    assert text == "Deus, status dos universos"
    assert language_code == "por"
    assert probability == 0.98
    assert [event[0] for event in repository.events] == [
        "voice.transcription.requested",
        "voice.transcription.succeeded",
    ]


@pytest.mark.asyncio
async def test_voice_transcribe_endpoint_returns_text():
    async def fake_creator():
        return TokenPayload(sub="creator-1", type="access", jti="jti", exp=9999999999)

    app.dependency_overrides[get_sovereign_creator] = fake_creator
    app.dependency_overrides[voice_service_dependency] = lambda: FakeVoiceService()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/voice/transcribe",
                headers={"Authorization": "Bearer test-token", "Content-Type": "audio/webm"},
                content=b"voice-bytes",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "text": "Deus, status dos universos",
        "language_code": "por",
        "language_probability": 0.98,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status"),
    [
        (VOICE_TRANSCRIPTION_DISABLED("disabled"), 501),
        (VOICE_TRANSCRIPTION_EMPTY_AUDIO("empty"), 422),
        (VOICE_TRANSCRIPTION_TOO_LARGE("large"), 422),
        (VOICE_TRANSCRIPTION_UNAVAILABLE("down"), 503),
    ],
)
async def test_voice_transcribe_endpoint_maps_failures(error, status):
    async def fake_creator():
        return TokenPayload(sub="creator-1", type="access", jti="jti", exp=9999999999)

    class RaisingTranscriptionService:
        async def transcribe(self, actor, audio, content_type, correlation_id):
            raise error

    app.dependency_overrides[get_sovereign_creator] = fake_creator
    app.dependency_overrides[voice_service_dependency] = lambda: RaisingTranscriptionService()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/voice/transcribe",
                headers={"Content-Type": "audio/webm"},
                content=b"voice",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == status
