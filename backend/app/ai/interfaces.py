from __future__ import annotations

from typing import Protocol


class LanguageModel(Protocol):
    async def generate(self, prompt: str, max_tokens: int | None = None) -> str:
        ...


class EmbeddingModel(Protocol):
    async def embed(self, text: str) -> list[float]:
        ...
