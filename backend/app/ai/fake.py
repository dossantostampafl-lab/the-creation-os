from __future__ import annotations


class FakeEmbeddingModel:
    """Legacy compatibility adapter; actual provider resolution occurs at invocation."""

    async def embed(self, text: str) -> list[float]:
        from app.ai.embeddings import build_embedding_model

        model = build_embedding_model()
        return await model.embed(text)
