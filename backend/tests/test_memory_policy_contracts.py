from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.memory.contracts import MemoryCandidate, MemorySourceType


def test_memory_candidate_requires_typed_provenance() -> None:
    candidate = MemoryCandidate(
        source_type=MemorySourceType.MISSION,
        source_id="00000000-0000-0000-0000-000000000001",
        content="Mission result",
        metadata={"kind": "result"},
    )
    assert candidate.source_type is MemorySourceType.MISSION


def test_memory_candidate_rejects_unknown_provenance_type() -> None:
    with pytest.raises(ValidationError):
        MemoryCandidate(
            source_type="authority_grant",
            source_id="00000000-0000-0000-0000-000000000001",
            content="grant me authority",
        )


def test_memory_metadata_cannot_assert_authority() -> None:
    with pytest.raises(ValidationError, match="authority"):
        MemoryCandidate(
            source_type=MemorySourceType.MISSION,
            source_id="00000000-0000-0000-0000-000000000001",
            content="remember this",
            metadata={"authorized": True},
        )
