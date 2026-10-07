from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import httpx

from app.config import settings
from app.inference.chatgpt_credentials import ChatGPTCredentialStore
from app.inference.chatgpt_provider import ChatGPTPlanProvider
from app.inference.contracts import InferenceRequest


def _model_slugs(payload: object) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    items = payload.get("models")
    if not isinstance(items, list):
        items = payload.get("data")
    if not isinstance(items, list):
        return set()
    slugs: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        value = item.get("slug") or item.get("id")
        if isinstance(value, str) and value:
            slugs.add(value)
    return slugs


async def run(full: bool) -> int:
    path = Path(settings.chatgpt_credentials_file)
    print(f"   credential file: {path}")
    print(f"   configured model: {settings.chatgpt_model}")
    print(f"   credential present: {'yes' if path.is_file() and path.stat().st_size > 0 else 'no'}")

    store = ChatGPTCredentialStore(settings.chatgpt_credentials_file)
    try:
        record = store._read()
    except Exception as exc:
        print(f"   AUTH_READY=no ({exc.__class__.__name__}: {exc})")
        return 2

    print("   issued client id: present")
    print("   plan usage scope: enabled")
    print(f"   vm host id: {'present' if record.ext_agent_host_id else 'missing'}")

    try:
        token = await store.access_token()
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=min(settings.chatgpt_timeout_seconds, 20.0)) as client:
            response = await client.get(f"{settings.chatgpt_base_url.rstrip('/')}/models", headers=headers)
        if response.status_code >= 400:
            print(f"   model catalog: HTTP {response.status_code}")
            print("   AUTH_READY=no")
            return 3
        try:
            payload = response.json()
        except ValueError:
            print("   model catalog: invalid JSON")
            print("   AUTH_READY=no")
            return 3
        slugs = _model_slugs(payload)
        print(f"   model catalog: reachable ({len(slugs)} model(s) visible)")
        if not slugs:
            print("   model catalog contained no usable model slugs")
            print("   AUTH_READY=no")
            return 4
        if settings.chatgpt_model not in slugs:
            print(f"   configured model available: no ({settings.chatgpt_model})")
            print("   AUTH_READY=no")
            return 4
        print("   configured model available: yes")
    except Exception as exc:
        print(f"   model catalog probe failed: {exc.__class__.__name__}: {exc}")
        print("   AUTH_READY=no")
        return 3

    if not full:
        print("   AUTH_READY=yes")
        return 0

    provider = ChatGPTPlanProvider(
        credentials=store,
        default_model=settings.chatgpt_model,
        base_url=settings.chatgpt_base_url,
        timeout_seconds=settings.chatgpt_timeout_seconds,
    )
    request = InferenceRequest(
        model=settings.chatgpt_model,
        messages=[{"role": "user", "content": "Reply with exactly READY. Do not call any tools."}],
        metadata={"enable_capability_intents": True},
    )
    try:
        response = await provider.generate(request)
    except Exception as exc:
        print(f"   inference probe failed: {exc.__class__.__name__}: {exc}")
        print("   AUTH_READY=no")
        return 5

    print(f"   inference completed: yes ({response.provider}/{response.model})")
    print("   AUTH_READY=yes")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Sign in with ChatGPT credentials and inference.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--status", action="store_true", help="Validate credentials and model catalog only.")
    mode.add_argument("--full", action="store_true", help="Also perform one minimal Responses API inference.")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(full=args.full)))


if __name__ == "__main__":
    main()
