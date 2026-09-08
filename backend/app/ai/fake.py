from __future__ import annotations

from app.config import settings


class FakeLanguageModel:
    def __init__(self) -> None:
        if settings.app_env == "production":
            raise RuntimeError("fake language model is forbidden in production")

    async def generate(self, prompt: str, max_tokens: int | None = None) -> str:
        return "Simulação de resposta do modelo fake para classificação e análise."


class FakeEmbeddingModel:
    def __init__(self) -> None:
        if settings.app_env == "production":
            raise RuntimeError("fake embedding model is forbidden in production")

    async def embed(self, text: str) -> list[float]:
        return [float(ord(c) % 10) for c in text[:8]] + [0.0] * max(0, 8 - len(text[:8]))
