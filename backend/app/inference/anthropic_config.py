from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from pydantic.v1 import SecretStr

DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
DEFAULT_MAX_OUTPUT_TOKENS = 4096


@dataclass(frozen=True)
class AnthropicConfig:
    base_url: str
    model: str
    api_key: SecretStr
    timeout_seconds: float
    max_output_tokens: int


def load_anthropic_config() -> AnthropicConfig:
    raw_api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not raw_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")

    model = os.getenv("ANTHROPIC_MODEL", "").strip()
    if not model:
        raise RuntimeError("ANTHROPIC_MODEL is required when LLM_PROVIDER=anthropic")

    base_url = os.getenv("ANTHROPIC_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("ANTHROPIC_BASE_URL must use http or https")

    raw_timeout = os.getenv("ANTHROPIC_TIMEOUT_SECONDS", "60").strip()
    try:
        timeout_seconds = float(raw_timeout)
    except ValueError as exc:
        raise RuntimeError("ANTHROPIC_TIMEOUT_SECONDS must be numeric") from exc
    if timeout_seconds <= 0:
        raise RuntimeError("ANTHROPIC_TIMEOUT_SECONDS must be greater than zero")

    raw_max_tokens = os.getenv("ANTHROPIC_MAX_OUTPUT_TOKENS", str(DEFAULT_MAX_OUTPUT_TOKENS)).strip()
    try:
        max_output_tokens = int(raw_max_tokens)
    except ValueError as exc:
        raise RuntimeError("ANTHROPIC_MAX_OUTPUT_TOKENS must be an integer") from exc
    if max_output_tokens <= 0:
        raise RuntimeError("ANTHROPIC_MAX_OUTPUT_TOKENS must be greater than zero")

    return AnthropicConfig(
        base_url=base_url,
        model=model,
        api_key=SecretStr(raw_api_key),
        timeout_seconds=timeout_seconds,
        max_output_tokens=max_output_tokens,
    )
