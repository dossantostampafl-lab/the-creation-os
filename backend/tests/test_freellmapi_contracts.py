from dataclasses import FrozenInstanceError

import pytest

from app.ai.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnsupportedCapabilityError,
    LLMUpstreamResponseError,
)
from app.ai.interfaces import IntelligenceProvider, LanguageModel
from app.ai.types import (
    HealthState,
    LLMCapability,
    LLMMessage,
    LLMRequest,
    LLMResult,
    LLMRole,
    LLMUsage,
    ProviderHealth,
)


def test_request_and_result_types_are_immutable() -> None:
    request = LLMRequest(
        messages=(LLMMessage(role=LLMRole.USER, content="hello"),),
        model=None,
        max_tokens=64,
        capabilities=frozenset({LLMCapability.TEXT}),
        mission_id="mission-1",
        agent_id="agent-1",
    )
    result = LLMResult(
        text="world",
        provider="freellmapi",
        model="auto",
        finish_reason="stop",
        usage=LLMUsage(input_tokens=2, output_tokens=1, total_tokens=3),
    )

    with pytest.raises(FrozenInstanceError):
        request.model = "other"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.text = "changed"  # type: ignore[misc]


def test_contract_enums_define_phase_one_capabilities_and_health_states() -> None:
    assert {item.value for item in LLMCapability} == {
        "text",
        "streaming",
        "tools",
        "structured_output",
        "vision",
        "embeddings",
    }
    assert {item.value for item in HealthState} == {
        "healthy",
        "degraded",
        "rate_limited",
        "unavailable",
        "disabled_no_credential",
    }
    assert LLMRole.USER.value == "user"


def test_provider_health_carries_only_normalized_metadata() -> None:
    health = ProviderHealth(
        provider="freellmapi",
        state=HealthState.HEALTHY,
        model_count=12,
        detail=None,
    )

    assert health.provider == "freellmapi"
    assert health.model_count == 12
    assert health.detail is None


def test_error_hierarchy_is_normalized_under_llm_error() -> None:
    error_types = (
        LLMConfigurationError,
        LLMAuthenticationError,
        LLMRateLimitError,
        LLMTimeoutError,
        LLMProviderUnavailableError,
        LLMUpstreamResponseError,
        LLMUnsupportedCapabilityError,
    )

    assert all(issubclass(error_type, LLMError) for error_type in error_types)


def test_legacy_and_rich_protocols_remain_available() -> None:
    assert hasattr(LanguageModel, "generate")
    assert hasattr(IntelligenceProvider, "execute")
    assert hasattr(IntelligenceProvider, "health")
