from __future__ import annotations

import os
import re
from dataclasses import dataclass

from pydantic.v1 import SecretStr

from app.inference.base_url import checked_base_url
from app.inference.provider_common import positive_env, required_env

DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
DEFAULT_MAX_OUTPUT_TOKENS = 4096


@dataclass(frozen=True)
class AnthropicConfig:
    base_url: str
    model: str
    api_key: SecretStr
    workspace_id: str | None
    timeout_seconds: float
    max_output_tokens: int


def load_anthropic_config() -> AnthropicConfig:
    api_key = required_env("ANTHROPIC_API_KEY", "anthropic")
    model = required_env("ANTHROPIC_MODEL", "anthropic")

    workspace_id = os.getenv("ANTHROPIC_WORKSPACE_ID", "").strip() or None
    if workspace_id is not None and re.fullmatch(r"wrkspc_[A-Za-z0-9]+", workspace_id) is None:
        raise RuntimeError("ANTHROPIC_WORKSPACE_ID must be a workspace ID")

    base_url = checked_base_url(
        "ANTHROPIC_BASE_URL",
        os.getenv("ANTHROPIC_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL,
    )

    return AnthropicConfig(
        base_url=base_url,
        model=model,
        api_key=SecretStr(api_key),
        workspace_id=workspace_id,
        timeout_seconds=positive_env("ANTHROPIC_TIMEOUT_SECONDS", "60", float),
        max_output_tokens=positive_env("ANTHROPIC_MAX_OUTPUT_TOKENS", str(DEFAULT_MAX_OUTPUT_TOKENS), int),
    )
