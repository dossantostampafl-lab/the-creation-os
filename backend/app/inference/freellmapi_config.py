from __future__ import annotations

import os
from dataclasses import dataclass

from pydantic.v1 import SecretStr

from app.inference.base_url import checked_base_url
from app.inference.provider_common import positive_env, required_env


@dataclass(frozen=True)
class FreeLLMAPIConfig:
    # None when the gateway needs no key. FreeLLMAPI runs on this machine and can be configured without one.
    api_key: SecretStr | None
    base_url: str
    timeout_seconds: float


def load_freellmapi_config() -> FreeLLMAPIConfig:
    raw_key = os.getenv("FREELLMAPI_API_KEY", "").strip()
    base_url = checked_base_url("FREELLMAPI_BASE_URL", required_env("FREELLMAPI_BASE_URL", "freellmapi"))
    return FreeLLMAPIConfig(
        api_key=SecretStr(raw_key) if raw_key else None,
        base_url=base_url,
        timeout_seconds=positive_env("FREELLMAPI_TIMEOUT_SECONDS", "60", float),
    )


def load_freellmapi_model() -> str:
    return required_env("FREELLMAPI_MODEL", "freellmapi")
