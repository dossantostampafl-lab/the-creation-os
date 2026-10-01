from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Protocol


class RealtimeTTS(Protocol):
    async def send_text(self, text: str) -> None: ...
    async def finish(self) -> None: ...
    async def receive_audio(self) -> bytes | None: ...


TTSFactory = Callable[[], AbstractAsyncContextManager[RealtimeTTS]]


class VoiceAcknowledgementCache:
    def __init__(
        self,
        factory: TTSFactory,
        *,
        text: str = "Estou aqui.",
        timeout_seconds: float = 20.0,
    ) -> None:
        if not text.strip():
            raise ValueError("acknowledgement text is required")
        if timeout_seconds <= 0:
            raise ValueError("acknowledgement timeout must be positive")
        self._factory = factory
        self._text = text.strip()
        self._timeout_seconds = timeout_seconds
        self._lock = asyncio.Lock()
        self._audio: bytes | None = None

    async def get(self) -> bytes:
        if self._audio is not None:
            return self._audio

        async with self._lock:
            if self._audio is not None:
                return self._audio

            chunks: list[bytes] = []
            async with asyncio.timeout(self._timeout_seconds):
                async with self._factory() as tts:
                    await tts.send_text(self._text)
                    await tts.finish()
                    while True:
                        chunk = await tts.receive_audio()
                        if chunk is None:
                            break
                        if chunk:
                            chunks.append(chunk)

            audio = b"".join(chunks)
            if not audio:
                raise RuntimeError("Voice acknowledgement returned empty audio")
            self._audio = audio
            return audio
