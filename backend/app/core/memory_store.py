from __future__ import annotations

from typing import Any, Protocol


class MemoryStore(Protocol):
    """Common read/write contract for the four memory layers (conversation,
    mission, universe, conscious). What a "key" and a returned item mean
    differs per implementation (see ScopedMemoryService for the three
    key/value layers vs ConsciousMemoryService for the embedding-indexed
    fourth layer), but every layer exposes exactly these four operations."""

    async def get(self, key: str) -> Any | None: ...

    async def set(self, key: str, value: dict[str, Any]) -> Any: ...

    async def search(self, query: str | None = None, *, limit: int = 20) -> list[Any]: ...

    async def delete(self, key: str) -> bool: ...
