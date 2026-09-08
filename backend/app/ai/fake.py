from __future__ import annotations

from app.config import settings


class FakeLanguageModel:
    async def generate(self, prompt: str, max_tokens: int | None = None) -> str:
        if settings.app_env == "production":
            raise RuntimeError("fake language model is forbidden in production")
        return "Simulação de resposta do modelo fake para classificação e análise."


class FakeEmbeddingModel:
    """Legacy compatibility adapter; actual provider resolution occurs at invocation."""

    async def embed(self, text: str) -> list[float]:
        from app.ai.embeddings import build_embedding_model

        model = build_embedding_model()
        return await model.embed(text)
