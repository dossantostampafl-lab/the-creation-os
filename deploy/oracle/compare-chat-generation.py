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
    cases = [
        ("literal", "Responda apenas: voz local ativa", "voz local ativa"),
        ("punctuation", "Responda exatamente com este texto, sem aspas: SINAL-73: pronto!", "SINAL-73: pronto!"),
        ("json", 'Responda somente com este JSON, sem bloco de código: {"estado":"pronto","passo":2}', '{"estado":"pronto","passo":2}'),
        ("list", "Responda exatamente com estas duas linhas, mantendo os marcadores de hífen, sem introdução:\n- alfa\n- beta", "- alfa\n- beta"),
        ("arithmetic", "Quanto é dois mais dois? Responda apenas com o número.", "4"),
        ("context", "Qual estilo de voz eu acabei de preferir? Responda em uma frase.", ("masculin", "grav", "seren")),
    ]
    for selected_model, (name, question, expected) in [(model, case) for model in ("gpt-oss-20b", "qwen3.8-27b") for case in cases]:
        messages = packet.messages[:-2] + [{"role": "user", "content": "Prefiro sua voz masculina, grave e serena."}] + [packet.messages[-2], {"role": "user", "content": question}]
        budget = 512
        started = time.monotonic()
        try:
            response = await asyncio.wait_for(provider.generate(InferenceRequest(messages=messages,
                model=selected_model,
                requirements=ModelRequirements(preferred_provider="freellmapi", max_output_tokens=budget))), 25)
            print(json.dumps({"requested_model": selected_model, "case": name, "ms": round((time.monotonic()-started)*1000),
                "input_bytes": len(json.dumps(messages).encode()), "exact": (all(word in response.content.casefold() for word in expected) if isinstance(expected, tuple) else response.content == expected),
                "model": response.model, "finish": response.finish_reason, "usage": response.usage}), flush=True)
        except Exception as exc:
            print(json.dumps({"requested_model": selected_model, "case": name, "error": type(exc).__name__}), flush=True)


asyncio.run(main())
