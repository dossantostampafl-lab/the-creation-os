from __future__ import annotations

import os
from dataclasses import dataclass

from pydantic.v1 import SecretStr

from app.config import settings

# Models that accept the server-side refusal fallback ("fallbacks": "default").
FALLBACK_CAPABLE_MODELS = frozenset({"claude-opus-5", "claude-fable-5-1"})
EFFORT_LEVELS = frozenset({"low", "medium", "high", "xhigh", "max"})


@dataclass(frozen=True)
class AnthropicConfig:
    api_key: SecretStr
    model: str
    timeout_seconds: float
    max_output_tokens: int
    effort: str | None
    refusal_fallback: bool


def load_anthropic_config() -> AnthropicConfig:
    raw_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not raw_key and settings.llm_api_key is not None:
        raw_key = settings.llm_api_key.get_secret_value().strip()
    if not raw_key:
        raise RuntimeError("ANTHROPIC_API_KEY (or LLM_API_KEY) is required when LLM_PROVIDER=anthropic")

    model = settings.llm_model.strip()
    if not model or model == "fake":
        raise RuntimeError("LLM_MODEL must name a Claude model (for example claude-opus-5) when LLM_PROVIDER=anthropic")

    raw_timeout = os.getenv("ANTHROPIC_TIMEOUT_SECONDS", "120").strip()
    try:
        timeout_seconds = float(raw_timeout)
    except ValueError as exc:
        raise RuntimeError("ANTHROPIC_TIMEOUT_SECONDS must be numeric") from exc
    if timeout_seconds <= 0:
        raise RuntimeError("ANTHROPIC_TIMEOUT_SECONDS must be greater than zero")

    raw_max_tokens = os.getenv("ANTHROPIC_MAX_OUTPUT_TOKENS", "16000").strip()
    try:
        max_output_tokens = int(raw_max_tokens)
    except ValueError as exc:
        raise RuntimeError("ANTHROPIC_MAX_OUTPUT_TOKENS must be an integer") from exc
    if max_output_tokens <= 0:
        raise RuntimeError("ANTHROPIC_MAX_OUTPUT_TOKENS must be greater than zero")

    effort = os.getenv("ANTHROPIC_EFFORT", "").strip().lower() or None
    if effort is not None and effort not in EFFORT_LEVELS:
        raise RuntimeError(f"ANTHROPIC_EFFORT must be one of: {', '.join(sorted(EFFORT_LEVELS))}")

    fallback_setting = os.getenv("ANTHROPIC_REFUSAL_FALLBACK", "default").strip().lower()
    if fallback_setting not in {"default", "off"}:
        raise RuntimeError("ANTHROPIC_REFUSAL_FALLBACK must be 'default' or 'off'")

    return AnthropicConfig(
        api_key=SecretStr(raw_key),
        model=model,
        timeout_seconds=timeout_seconds,
        max_output_tokens=max_output_tokens,
        effort=effort,
        refusal_fallback=fallback_setting == "default" and model in FALLBACK_CAPABLE_MODELS,
    )
