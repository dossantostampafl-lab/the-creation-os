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
