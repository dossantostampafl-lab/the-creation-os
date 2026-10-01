from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from app.voice_session.acknowledgement import VoiceAcknowledgementCache


class FakeTTS:
    def __init__(self) -> None:
        self.text: list[str] = []
        self.finished = False
        self.audio = [b"pcm-a", b"pcm-b", None]

    async def send_text(self, text: str) -> None:
        self.text.append(text)

    async def finish(self) -> None:
        self.finished = True

    async def receive_audio(self) -> bytes | None:
        return self.audio.pop(0)


@pytest.mark.asyncio
async def test_acknowledgement_is_elevenlabs_pcm_and_cached():
    instances: list[FakeTTS] = []

    @asynccontextmanager
    async def factory():
        tts = FakeTTS()
        instances.append(tts)
        yield tts

    cache = VoiceAcknowledgementCache(factory, text="Estou aqui.")

    first = await cache.get()
    second = await cache.get()

    assert first == b"pcm-apcm-b"
    assert second == first
    assert len(instances) == 1
    assert instances[0].text == ["Estou aqui."]
    assert instances[0].finished is True


@pytest.mark.asyncio
async def test_acknowledgement_refuses_empty_audio():
    @asynccontextmanager
    async def factory():
        tts = FakeTTS()
        tts.audio = [None]
        yield tts

    cache = VoiceAcknowledgementCache(factory)

    with pytest.raises(RuntimeError, match="empty"):
        await cache.get()
