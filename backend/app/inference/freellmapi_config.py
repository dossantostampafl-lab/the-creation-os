from __future__ import annotations

from dataclasses import dataclass

from pydantic.v1 import SecretStr

from app.inference.base_url import checked_base_url
from app.inference.provider_common import positive_env, required_env


@dataclass(frozen=True)
class FreeLLMAPIConfig:
    api_key: SecretStr
    base_url: str
    timeout_seconds: float


def load_freellmapi_config() -> FreeLLMAPIConfig:
    api_key = required_env("FREELLMAPI_API_KEY", "freellmapi")
    base_url = checked_base_url("FREELLMAPI_BASE_URL", required_env("FREELLMAPI_BASE_URL", "freellmapi"))
    return FreeLLMAPIConfig(
        api_key=SecretStr(api_key),
        base_url=base_url,
        timeout_seconds=positive_env("FREELLMAPI_TIMEOUT_SECONDS", "60", float),
    )


def load_freellmapi_model() -> str:
    return required_env("FREELLMAPI_MODEL", "freellmapi")
