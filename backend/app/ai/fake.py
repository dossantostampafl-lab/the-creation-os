from __future__ import annotations

from typing import Any

from app.config import settings


class FakeLanguageModel:
    def __init__(self) -> None:
        if settings.app_env == "production":
            raise RuntimeError("fake language model is forbidden in production")

    async def generate(self, prompt: str, max_tokens: int | None = None) -> str:
        return "Simulação de resposta do modelo fake para classificação e análise."


class FakeEmbeddingModel:
    """Legacy compatibility constructor; provider selection is centralized in ai.embeddings."""

    def __new__(cls) -> Any:
        from app.ai.embeddings import build_embedding_model

        return build_embedding_model()
