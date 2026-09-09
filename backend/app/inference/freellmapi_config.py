from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class FreeLLMAPIConfig:
    base_url: str
    timeout_seconds: float


def load_freellmapi_config() -> FreeLLMAPIConfig:
    base_url = os.getenv("FREELLMAPI_BASE_URL", "http://freellmapi:3001/v1").strip()
    if not base_url:
        raise RuntimeError("FREELLMAPI_BASE_URL must not be empty")

    raw_timeout = os.getenv("FREELLMAPI_TIMEOUT_SECONDS", "60").strip()
    try:
        timeout_seconds = float(raw_timeout)
    except ValueError as exc:
        raise RuntimeError("FREELLMAPI_TIMEOUT_SECONDS must be numeric") from exc
    if timeout_seconds <= 0:
        raise RuntimeError("FREELLMAPI_TIMEOUT_SECONDS must be greater than zero")

    return FreeLLMAPIConfig(base_url=base_url, timeout_seconds=timeout_seconds)
