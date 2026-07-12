from __future__ import annotations


class FakeLanguageModel:
    async def generate(self, prompt: str, max_tokens: int | None = None) -> str:
        return "Simulação de resposta do modelo fake para classificação e análise."


class FakeEmbeddingModel:
    async def embed(self, text: str) -> list[float]:
        return [float(ord(c) % 10) for c in text[:8]] + [0.0] * max(0, 8 - len(text[:8]))
