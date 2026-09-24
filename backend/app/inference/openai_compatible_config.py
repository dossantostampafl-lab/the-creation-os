from __future__ import annotations

import os
from dataclasses import dataclass

from pydantic.v1 import SecretStr

from app.inference.base_url import checked_base_url


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    base_url: str
    model: str
    api_key: SecretStr | None
    timeout_seconds: float


def load_openai_compatible_config() -> OpenAICompatibleConfig:
    raw_base_url = os.getenv("OPENAI_COMPATIBLE_BASE_URL", "").strip()
    if not raw_base_url:
        raise RuntimeError(
            "OPENAI_COMPATIBLE_BASE_URL is required when LLM_PROVIDER=openai_compatible"
        )
    base_url = checked_base_url("OPENAI_COMPATIBLE_BASE_URL", raw_base_url)

    model = os.getenv("OPENAI_COMPATIBLE_MODEL", "").strip()
    if not model:
        raise RuntimeError(
            "OPENAI_COMPATIBLE_MODEL is required when LLM_PROVIDER=openai_compatible"
        )

    raw_api_key = os.getenv("OPENAI_COMPATIBLE_API_KEY", "").strip()
    api_key = SecretStr(raw_api_key) if raw_api_key else None

    raw_timeout = os.getenv("OPENAI_COMPATIBLE_TIMEOUT_SECONDS", "60").strip()
    try:
        timeout_seconds = float(raw_timeout)
    except ValueError as exc:
        raise RuntimeError("OPENAI_COMPATIBLE_TIMEOUT_SECONDS must be numeric") from exc
    if timeout_seconds <= 0:
        raise RuntimeError(
            "OPENAI_COMPATIBLE_TIMEOUT_SECONDS must be greater than zero"
        )

    return OpenAICompatibleConfig(
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )
