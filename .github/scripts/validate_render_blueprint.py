#!/usr/bin/env python3
"""Check render.yaml beyond YAML syntax: a misspelled key must not reach a deploy.

Render only reports a bad blueprint when someone tries to deploy it, so the settings the
runtime needs are asserted here instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

BLUEPRINT = Path(__file__).resolve().parents[2] / "render.yaml"

# What each service must be able to read for the documented setup to work at all.
REQUIRED: dict[str, set[str]] = {
    "creation-api": {
        "APP_ENV", "APP_SECRET_KEY", "DATABASE_URL", "REDIS_URL", "CORS_ALLOW_ORIGINS",
        "CREATOR_BOOTSTRAP_USERNAME", "CREATOR_BOOTSTRAP_PASSWORD",
        "LLM_PROVIDER", "LLM_FALLBACK_PROVIDERS", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
        "FREELLMAPI_API_KEY", "FREELLMAPI_MODEL", "FREELLMAPI_BASE_URL",
        "TRINITY_ENABLED", "ELEVENLABS_ENABLED", "ELEVENLABS_API_KEY",
    },
    "creation-worker": {
        "APP_ENV", "APP_SECRET_KEY", "DATABASE_URL", "REDIS_URL",
        "LLM_PROVIDER", "LLM_FALLBACK_PROVIDERS", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
        "FREELLMAPI_API_KEY", "FREELLMAPI_MODEL", "FREELLMAPI_BASE_URL",
    },
}

VALID_ENV_VAR_KEYS = {"key", "value", "sync", "fromDatabase", "fromService", "generateValue"}


def main() -> int:
    blueprint = yaml.safe_load(BLUEPRINT.read_text())
    problems: list[str] = []

    services = {service["name"]: service for service in blueprint.get("services", [])}
    for name, required in REQUIRED.items():
        service = services.get(name)
        if service is None:
            problems.append(f"{name}: service missing from the blueprint")
            continue
        env_vars = service.get("envVars", [])
        keys = [item["key"] for item in env_vars]
        for item in env_vars:
            unknown = set(item) - VALID_ENV_VAR_KEYS
            if unknown:
                problems.append(f"{name}/{item['key']}: unknown field(s) {sorted(unknown)}")
            if not ({"value", "sync", "fromDatabase", "fromService", "generateValue"} & set(item)):
                problems.append(f"{name}/{item['key']}: has no value, sync or source")
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        if duplicates:
            problems.append(f"{name}: duplicate env var(s) {duplicates}")
        missing = sorted(required - set(keys))
        if missing:
            problems.append(f"{name}: missing env var(s) {missing}")

    for problem in problems:
        print(f"render.yaml: {problem}", file=sys.stderr)
    if problems:
        return 1
    print(f"render.yaml: {len(services)} services validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
