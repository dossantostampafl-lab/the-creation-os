"""Compare bounded generation settings with the real context builder; no reply logs."""
import asyncio
import json
import time

import httpx

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.inference.bootstrap import build_model_router
from app.inference.contracts import InferenceRequest, ModelRequirements
from app.services.deus_context import DeusContextBuilder


async def main():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000/api/v1", timeout=10) as client:
        response = await client.post("/auth/login", json={"username": settings.creator_bootstrap_username,
            "password": settings.creator_bootstrap_password.get_secret_value()})
        response.raise_for_status()
        client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
        me = await client.get("/auth/me")
        me.raise_for_status()
        created = await client.post("/conversations", json={"title": "Synthetic chat latency comparison"})
        created.raise_for_status()
    query = "Responda apenas: voz local ativa"
    packet = await DeusContextBuilder(AsyncSessionLocal).build(me.json()["id"], created.json()["id"], query, "text")
    router = build_model_router()
    provider = router.registry.get("freellmapi")
    for name in ["gemini-3.5-flash-lite", "gemini-2.5-flash-lite", "gemma-4-26b-a4b", "gpt-oss-20b"]:
        messages = packet.messages
        budget = 512
        started = time.monotonic()
        try:
            response = await asyncio.wait_for(provider.generate(InferenceRequest(messages=messages,
                model=name,
                requirements=ModelRequirements(preferred_provider="freellmapi", max_output_tokens=budget))), 25)
            print(json.dumps({"case": name, "ms": round((time.monotonic()-started)*1000),
                "input_bytes": len(json.dumps(messages).encode()), "exact": response.content == "voz local ativa",
                "model": response.model, "finish": response.finish_reason, "usage": response.usage}), flush=True)
        except Exception as exc:
            print(json.dumps({"case": name, "error": type(exc).__name__}), flush=True)


asyncio.run(main())
