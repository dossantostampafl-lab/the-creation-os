"""Generated agent profiles follow runtime routing; explicit pins remain authoritative."""
from typing import Any

from app.config import settings


def effective_agent_capabilities(capabilities: dict[str, Any]) -> dict[str, Any]:
    result = dict(capabilities)
    if (
        result.get("inference_routing") == "configured"
        and result.get("model") is None
        and not result.get("fallback_providers")
    ):
        chain = settings.inference_provider_chain
        result["inference_provider"] = chain[0]
        result["fallback_providers"] = chain[1:]
    return result
