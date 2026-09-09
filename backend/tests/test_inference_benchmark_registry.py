from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.inference.contracts import ProviderBenchmarkEvidence, ProviderHealth
from app.inference.registry import ProviderRegistry


class StubProvider:
    name = "gateway"

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, available=True)


def evidence(*, suite_id: str, score: float, observed_at: datetime) -> ProviderBenchmarkEvidence:
    return ProviderBenchmarkEvidence(
        provider="gateway",
        model="model-a",
        suite_id=suite_id,
        score=score,
        sample_count=100,
        observed_at=observed_at,
    )


def test_benchmark_evidence_is_validated_and_immutable() -> None:
    item = evidence(suite_id="suite-a", score=0.82, observed_at=datetime.now(UTC))

    with pytest.raises(ValidationError):
        item.score = 0.2

    with pytest.raises(ValidationError):
        ProviderBenchmarkEvidence(
            provider="gateway",
            model="model-a",
            suite_id="suite-b",
            score=1.1,
            sample_count=0,
            observed_at=datetime.now(UTC),
        )


def test_registry_rejects_duplicate_provider_model_suite_evidence() -> None:
    registry = ProviderRegistry()
    registry.register(StubProvider())
    item = evidence(suite_id="suite-a", score=0.8, observed_at=datetime.now(UTC))
    registry.register_benchmark_evidence(item)

    with pytest.raises(ValueError, match="benchmark evidence already registered"):
        registry.register_benchmark_evidence(item)


def test_registry_returns_latest_evidence_deterministically() -> None:
    registry = ProviderRegistry()
    registry.register(StubProvider())
    now = datetime.now(UTC)
    older = evidence(suite_id="suite-a", score=0.95, observed_at=now - timedelta(days=1))
    latest = evidence(suite_id="suite-b", score=0.80, observed_at=now)
    registry.register_benchmark_evidence(older)
    registry.register_benchmark_evidence(latest)

    assert registry.get_benchmark_evidence("gateway", "model-a") == latest
    assert registry.get_benchmark_evidence("gateway", "missing") is None
