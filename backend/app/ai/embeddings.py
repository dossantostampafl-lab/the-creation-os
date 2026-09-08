from __future__ import annotations

from typing import Any

import httpx

from app.ai.fake import FakeEmbeddingModel
from app.ai.interfaces import EmbeddingModel
from app.config import settings


class OpenAIEmbeddingModel:
    def __init__(self, *, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": text},
            )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        data = payload.get("data") or []
        if not data or not isinstance(data[0].get("embedding"), list):
            raise RuntimeError("embedding provider returned an invalid response")
        return [float(value) for value in data[0]["embedding"]]


def build_embedding_model() -> EmbeddingModel:
    provider = settings.embedding_provider.strip().lower()
    if provider == "fake":
        if settings.app_env == "production":
            raise RuntimeError("fake embedding provider is forbidden in production")
        return FakeEmbeddingModel()
    if provider == "openai":
        if settings.llm_api_key is None:
            raise RuntimeError("OpenAI embedding provider requires LLM_API_KEY")
        return OpenAIEmbeddingModel(
            api_key=settings.llm_api_key.get_secret_value(),
            model=settings.embedding_model,
        )
    raise RuntimeError(f"unsupported embedding provider: {provider}")
