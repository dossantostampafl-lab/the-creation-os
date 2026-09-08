from __future__ import annotations

from app.inference.openai_provider import OpenAIResponsesProvider


def test_openai_provider_normalizes_text_and_capability_intent_without_execution() -> None:
    content, metadata = OpenAIResponsesProvider._normalize_output({
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "I need an authorized action."}],
            },
            {
                "type": "function_call",
                "name": "capability_intent",
                "arguments": (
                    '{"capability":"echo","action":"say","resource":null,'
                    '"arguments":{"value":"hello"},"external_effect":false,'
                    '"idempotency_class":"SAFE","idempotency_key":null}'
                ),
            },
        ]
    })

    assert content == "I need an authorized action."
    assert metadata["capability_intent"]["capability"] == "echo"
    assert metadata["capability_intent"]["arguments"] == {"value": "hello"}


def test_openai_capability_tool_only_requests_policy_controlled_execution() -> None:
    tool = OpenAIResponsesProvider._capability_tool()
    assert tool["name"] == "capability_intent"
    assert tool["type"] == "function"
    assert "policy" in tool["description"].lower()
    assert tool["parameters"]["additionalProperties"] is False
