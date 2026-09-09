from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlparse

import httpx

from app.ai.interfaces import EmbeddingModel
from app.config import settings
from app.inference.freellmapi_config import load_freellmapi_config


class DeterministicTestEmbeddingModel:
    async def embed(self, text: str) -> list[float]:
        return [float(ord(c) % 10) for c in text[:8]] + [0.0] * max(0, 8 - len(text[:8]))


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


class FreeLLMAPIEmbeddingModel:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("FreeLLMAPI embedding API key is required")
        if not model.strip():
            raise ValueError("FreeLLMAPI embedding model is required")
        if timeout_seconds <= 0:
            raise ValueError("FreeLLMAPI embedding timeout must be greater than zero")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("FreeLLMAPI embedding base URL must use http or https")

        self._api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._transport = transport

    async def embed(self, text: str) -> list[float]:
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"model": self.model, "input": text},
                )
        except httpx.TimeoutException as exc:
            raise RuntimeError("FreeLLMAPI embedding request timed out") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError("FreeLLMAPI embedding network request failed") from exc

        if response.status_code >= 400:
            raise RuntimeError(
                f"FreeLLMAPI embedding upstream request failed with status {response.status_code}"
            )

        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError("FreeLLMAPI embedding provider returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("FreeLLMAPI embedding provider returned an invalid response")
        data = payload.get("data")
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise RuntimeError("FreeLLMAPI embedding provider returned an invalid response")
        embedding = data[0].get("embedding")
        if not isinstance(embedding, list):
            raise RuntimeError("FreeLLMAPI embedding provider returned an invalid response")
        try:
            return [float(value) for value in embedding]
        except (TypeError, ValueError) as exc:
            raise RuntimeError("FreeLLMAPI embedding provider returned an invalid response") from exc


def build_embedding_model() -> EmbeddingModel:
    provider = settings.embedding_provider.strip().lower()
    if provider == "fake":
        if settings.app_env == "production":
            raise RuntimeError("fake embedding provider is forbidden in production")
        return DeterministicTestEmbeddingModel()
    if provider == "openai":
        if settings.llm_api_key is None:
            raise RuntimeError("OpenAI embedding provider requires LLM_API_KEY")
        return OpenAIEmbeddingModel(
            api_key=settings.llm_api_key.get_secret_value(),
            model=settings.embedding_model,
        )
    if provider == "freellmapi":
        api_key = os.getenv("FREELLMAPI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("FreeLLMAPI embedding provider requires FREELLMAPI_API_KEY")
        if not settings.embedding_model.strip():
            raise RuntimeError("FreeLLMAPI embedding provider requires EMBEDDING_MODEL")
        gateway_config = load_freellmapi_config()
        return FreeLLMAPIEmbeddingModel(
            api_key=api_key,
            model=settings.embedding_model,
            base_url=gateway_config.base_url,
            timeout_seconds=gateway_config.timeout_seconds,
        )
    raise RuntimeError(f"unsupported embedding provider: {provider}")
