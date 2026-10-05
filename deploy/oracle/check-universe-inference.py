"""Synthetic, bounded API/worker comparison; never print credentials or reply text."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from collections import Counter

import httpx
from app.admin.seed import CANONICAL_UNIVERSES
from app.config import SUPPORTED_LLM_PROVIDERS, settings
from app.db.session import AsyncSessionLocal
from app.inference.bootstrap import build_model_router
from app.inference.contracts import InferenceRequest, ModelRequirements
from app.models.entities import Agent, Task
from sqlalchemy import select, text


def label(value: object) -> str:
    raw = str(value or "")
    return raw if re.fullmatch(r"[a-zA-Z0-9_.:/-]{1,100}", raw) else "unset-or-other"


def emit(**values: object) -> None:
    print(json.dumps({"service": label(os.getenv("DIAGNOSTIC_SERVICE")), **values}), flush=True)


def canonical_profile_shape(spec, capabilities):
    provider = capabilities.get("inference_provider")
    if (not isinstance(provider, str) or provider not in SUPPORTED_LLM_PROVIDERS
            or capabilities.get("inference_routing") not in (None, "configured")):
        return "custom"
    actual = {k: v for k, v in capabilities.items() if k not in {"inference_provider", "inference_routing"}}
    expected = {k: v for k, v in spec.capabilities.items() if k not in {"inference_provider", "inference_routing"}}
    return "generated-current" if actual == expected else "generated-legacy" if actual == {"description": spec.description} else "custom"


async def main() -> None:
    router = build_model_router()
    primary = settings.inference_provider_chain[0]
    provider = router.registry.get(primary)
    profile = router.registry.get_default_model_profile(primary)
    emit(check="configuration", chain=settings.inference_provider_chain,
         default_model=label(profile.model if profile else None),
         endpoint_hash=hashlib.sha256(str(getattr(provider, "_base_url", "")).encode()).hexdigest()[:12])
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        agents = (await session.scalars(select(Agent.capabilities_json))).all()
        groups = Counter((label((a or {}).get("inference_provider")), label((a or {}).get("model")))
                         for a in agents)
        emit(check="agent_configuration", groups=[{"provider": p, "model": m, "count": n}
                                                  for (p, m), n in sorted(groups.items())])
        specs = {spec.agent_code: spec for spec in CANONICAL_UNIVERSES}
        canonical = Counter()
        for agent in await session.scalars(select(Agent)):
            if agent.code not in specs:
                continue
            spec = specs[agent.code]
            canonical[canonical_profile_shape(spec, agent.capabilities_json or {})] += 1
        emit(check="canonical_profile_shapes", counts=dict(canonical))
        errors = (await session.scalars(select(Task.error_json).where(Task.status == "FAILED")
                                       .order_by(Task.created_at.desc()).limit(10))).all()
        for error in errors:
            detail = str((error or {}).get("detail", ""))
            reason = ("circuit_open" if detail == "provider circuit open" else
                      "rate_limit_cooldown" if detail == "provider rate-limit cooldown active" else
                      "upstream_status_" + detail.rsplit(" ", 1)[-1] if
                      re.fullmatch(r"FreeLLMAPI upstream request failed with status [0-9]{3}", detail) else
                      "network_error" if detail == "FreeLLMAPI network request failed" else
                      "invalid_response" if detail == "FreeLLMAPI returned an invalid response" else "other")
            emit(check="recent_failure", code=label((error or {}).get("code")),
                 provider=label((error or {}).get("provider")), reason=reason)
    if primary != "freellmapi":
        emit(check="generation", skipped="primary-not-freellmapi")
        return
    for tools in (False, True):
        request = InferenceRequest(
            messages=[{"role": "system", "content": "Answer the synthetic test question. Do not call tools."},
                      {"role": "user", "content": "Quanto é dois mais dois? Responda apenas 4."}],
            requirements=ModelRequirements(preferred_provider=primary, max_output_tokens=32),
            metadata={"enable_capability_intents": tools, "cache_policy": "bypass"})
        # Inspect only the response's shape/status; no body text or user data leaves the host.
        try:
            async with provider._client() as client:
                response = await asyncio.wait_for(client.post(
                    provider._base_url + "/chat/completions", json=provider._request_payload(request)), 20)
            try:
                payload = response.json()
            except ValueError:
                payload = None
            choices = payload.get("choices") if isinstance(payload, dict) else None
            message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
            emit(check="generation", tools=tools, status=response.status_code,
                 has_choices=isinstance(choices, list) and bool(choices),
                 has_text=isinstance(message, dict) and isinstance(message.get("content"), str))
        except (httpx.HTTPError, TimeoutError) as error:
            emit(check="generation", tools=tools, error_type=type(error).__name__)


if __name__ == "__main__":
    asyncio.run(main())
