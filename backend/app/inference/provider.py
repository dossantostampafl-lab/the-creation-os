from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from app.inference.contracts import InferenceRequest, InferenceResponse, ProviderHealth


class InferenceProvider(Protocol):
    name: str

    async def generate(self, request: InferenceRequest) -> InferenceResponse: ...

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]: ...

    async def health(self) -> ProviderHealth: ...
