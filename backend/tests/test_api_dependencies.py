from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.voice import service as voice_service_dependency
from app.auth.dependencies import get_sovereign_creator
from app.main import app
from app.schemas.auth import TokenPayload


class EchoVoiceService:
    def __init__(self) -> None:
        self.correlation_ids: list[str] = []

    async def synthesize(self, actor, text, correlation_id):  # type: ignore[no-untyped-def]
        self.correlation_ids.append(correlation_id)
        return b"audio", "audio/mpeg"


@pytest.fixture
def voice_service():
    fake = EchoVoiceService()

    async def fake_creator() -> TokenPayload:
        return TokenPayload(sub="creator-1", type="access", jti="jti", exp=9999999999)

    app.dependency_overrides[get_sovereign_creator] = fake_creator
    app.dependency_overrides[voice_service_dependency] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


async def post_voice(headers: dict[str, str]):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/api/v1/voice/synthesize", headers=headers, json={"text": "DEUS presente"})


@pytest.mark.asyncio
async def test_malformed_correlation_id_is_a_client_error(voice_service):
    response = await post_voice({"X-Correlation-ID": "not-a-uuid"})

    assert response.status_code == 400
    assert voice_service.correlation_ids == []


@pytest.mark.asyncio
async def test_correlation_id_is_normalized_or_generated(voice_service):
    provided = str(uuid.uuid4())
    assert (await post_voice({"X-Correlation-ID": provided.upper()})).status_code == 200
    assert (await post_voice({})).status_code == 200

    assert voice_service.correlation_ids[0] == provided
    assert uuid.UUID(voice_service.correlation_ids[1])
