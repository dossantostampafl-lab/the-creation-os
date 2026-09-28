from __future__ import annotations

import os
from dataclasses import dataclass

from pydantic.v1 import SecretStr

from app.inference.base_url import checked_base_url
from app.inference.provider_common import positive_env, required_env


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    base_url: str
    model: str
    api_key: SecretStr | None
    timeout_seconds: float


def load_openai_compatible_config() -> OpenAICompatibleConfig:
    base_url = checked_base_url(
        "OPENAI_COMPATIBLE_BASE_URL", required_env("OPENAI_COMPATIBLE_BASE_URL", "openai_compatible")
    )
    model = required_env("OPENAI_COMPATIBLE_MODEL", "openai_compatible")
    raw_api_key = os.getenv("OPENAI_COMPATIBLE_API_KEY", "").strip()
    return OpenAICompatibleConfig(
        base_url=base_url,
        model=model,
        api_key=SecretStr(raw_api_key) if raw_api_key else None,
        timeout_seconds=positive_env("OPENAI_COMPATIBLE_TIMEOUT_SECONDS", "60", float),
    )
