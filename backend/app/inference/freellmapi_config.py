from __future__ import annotations

import os
from dataclasses import dataclass

from pydantic.v1 import SecretStr


@dataclass(frozen=True)
class FreeLLMAPIConfig:
    api_key: SecretStr
    base_url: str
    timeout_seconds: float


def load_freellmapi_config() -> FreeLLMAPIConfig:
    raw_api_key = os.getenv("FREELLMAPI_API_KEY", "").strip()
    if not raw_api_key:
        raise RuntimeError("FREELLMAPI_API_KEY is required when LLM_PROVIDER=freellmapi")

    base_url = os.getenv("FREELLMAPI_BASE_URL", "").strip()
    if not base_url:
        raise RuntimeError("FREELLMAPI_BASE_URL is required when LLM_PROVIDER=freellmapi")

    raw_timeout = os.getenv("FREELLMAPI_TIMEOUT_SECONDS", "60").strip()
    try:
        timeout_seconds = float(raw_timeout)
    except ValueError as exc:
        raise RuntimeError("FREELLMAPI_TIMEOUT_SECONDS must be numeric") from exc
    if timeout_seconds <= 0:
        raise RuntimeError("FREELLMAPI_TIMEOUT_SECONDS must be greater than zero")

    return FreeLLMAPIConfig(
        api_key=SecretStr(raw_api_key),
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


def load_freellmapi_model() -> str:
    model = os.getenv("FREELLMAPI_MODEL", "").strip()
    if not model:
        raise RuntimeError("FREELLMAPI_MODEL is required when LLM_PROVIDER=freellmapi")
    return model
