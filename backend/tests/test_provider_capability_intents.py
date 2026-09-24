"""An Agent can only act by asking, so every operational provider must carry the ask.

The Agent never executes anything itself: it emits a capability_intent through the model's
tool mechanism, and the gateway's policy decides. A provider that cannot carry that request
leaves its Agents able to write text and nothing else.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.capabilities.contracts import CapabilityIntent
from app.inference.anthropic_provider import AnthropicProvider
from app.inference.contracts import InferenceRequest, InferenceUpstreamResponseError
from app.inference.freellmapi_provider import FreeLLMAPIProvider

INTENT = {
    "capability": "workspace",
    "action": "write",
    "resource": "notes.md",
    "arguments": {"content": "hello"},
    "external_effect": False,
    "idempotency_class": "IDEMPOTENT",
}


def anthropic_reply(blocks: list[dict]) -> dict:
    return {"model": "claude-model", "content": blocks, "stop_reason": "tool_use", "usage": {}}


def freellmapi_reply(message: dict) -> dict:
    return {"model": "auto", "choices": [{"message": message, "finish_reason": "tool_calls"}]}


def provider_for(name: str, payload: dict, captured: list[dict]):
    """A provider whose upstream answers with `payload` and records what it was sent."""
    def handler(http_request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(http_request.content))
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    if name == "anthropic":
        return AnthropicProvider(api_key="k", default_model="claude-model", transport=transport)
    return FreeLLMAPIProvider(
        api_key="freellmapi-k", default_model="auto",
        base_url="http://gateway.invalid/v1", transport=transport,
    )


def request_for(*, enable: bool) -> InferenceRequest:
    return InferenceRequest(
        messages=[{"role": "user", "content": "do the task"}],
        metadata={"enable_capability_intents": True} if enable else {},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["anthropic", "freellmapi"])
async def test_the_tool_is_offered_only_when_the_runtime_can_execute_capabilities(name: str) -> None:
    sent: list[dict] = []
    reply = (anthropic_reply([{"type": "text", "text": "done"}]) if name == "anthropic"
             else freellmapi_reply({"content": "done"}))
    provider = provider_for(name, reply, sent)

    await provider.generate(request_for(enable=False))
    assert "tools" not in sent[0]

    await provider.generate(request_for(enable=True))
    tools = sent[1]["tools"]
    assert len(tools) == 1
    name_of = tools[0]["name"] if name == "anthropic" else tools[0]["function"]["name"]
    assert name_of == "capability_intent"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["anthropic", "freellmapi"])
async def test_a_requested_capability_reaches_the_runtime_and_validates(name: str) -> None:
    reply = (anthropic_reply([{"type": "tool_use", "name": "capability_intent", "input": INTENT}])
             if name == "anthropic"
             else freellmapi_reply({"content": None, "tool_calls": [
                 {"function": {"name": "capability_intent", "arguments": json.dumps(INTENT)}}]}))
    provider = provider_for(name, reply, [])

    # A turn that only asks for a capability carries no text, and must not be an error.
    response = await provider.generate(request_for(enable=True))

    assert response.content == ""
    intent = CapabilityIntent.model_validate(response.metadata["capability_intent"])
    assert intent.capability == "workspace" and intent.action == "write"
    assert intent.external_effect is False


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["anthropic", "freellmapi"])
async def test_text_alongside_a_request_is_kept(name: str) -> None:
    reply = (anthropic_reply([
        {"type": "text", "text": "Writing the notes."},
        {"type": "tool_use", "name": "capability_intent", "input": INTENT},
    ]) if name == "anthropic" else freellmapi_reply({
        "content": "Writing the notes.",
        "tool_calls": [{"function": {"name": "capability_intent", "arguments": INTENT}}],
    }))
    provider = provider_for(name, reply, [])

    response = await provider.generate(request_for(enable=True))

    assert response.content == "Writing the notes."
    assert response.metadata["capability_intent"] == INTENT


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["anthropic", "freellmapi"])
async def test_an_ordinary_answer_carries_no_capability(name: str) -> None:
    reply = (anthropic_reply([{"type": "text", "text": "No capability needed."}]) if name == "anthropic"
             else freellmapi_reply({"content": "No capability needed."}))
    provider = provider_for(name, reply, [])

    response = await provider.generate(request_for(enable=True))

    assert response.content == "No capability needed."
    assert "capability_intent" not in response.metadata


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["anthropic", "freellmapi"])
async def test_an_unreadable_request_is_not_smuggled_through_as_an_empty_answer(name: str) -> None:
    """Malformed tool arguments must fail loudly, not look like a silent empty reply."""
    reply = (anthropic_reply([{"type": "tool_use", "name": "capability_intent", "input": "not-an-object"}])
             if name == "anthropic"
             else freellmapi_reply({"content": None, "tool_calls": [
                 {"function": {"name": "capability_intent", "arguments": "{not json"}}]}))
    provider = provider_for(name, reply, [])

    with pytest.raises(InferenceUpstreamResponseError):
        await provider.generate(request_for(enable=True))


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["anthropic", "freellmapi"])
async def test_another_tool_is_ignored(name: str) -> None:
    """Only capability_intent crosses into the authorization path."""
    reply = (anthropic_reply([
        {"type": "text", "text": "ok"},
        {"type": "tool_use", "name": "something_else", "input": {"capability": "workspace"}},
    ]) if name == "anthropic" else freellmapi_reply({
        "content": "ok",
        "tool_calls": [{"function": {"name": "something_else", "arguments": "{}"}}],
    }))
    provider = provider_for(name, reply, [])

    response = await provider.generate(request_for(enable=True))

    assert "capability_intent" not in response.metadata
