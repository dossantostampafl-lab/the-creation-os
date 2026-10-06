import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import settings

PROBE = Path(__file__).resolve().parents[2] / "deploy/oracle/check-chat-instructions.py"


@pytest.mark.parametrize("answer, expected, ok", [
    ("voz local ativa", "voz local ativa", True),
    ("Voz local está ativa.", "voz local ativa", False),
    ("SINAL-73: pronto!", "SINAL-73: pronto!", True),
    ("Sinal-73: pronto", "SINAL-73: pronto!", False),
    ("- alfa\n- beta", "- alfa\n- beta", True),
    ("alfa e beta", "- alfa\n- beta", False),
    ("4", "4", True),
    ("O resultado é 4.", "4", False),
])
def test_chat_probe_rejects_paraphrases_and_extra_text(answer, expected, ok):
    probe = runpy.run_path(str(PROBE))
    assert probe["matches"](answer, expected) is ok


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "wrong-answer", "provider-error"])
async def test_chat_probe_reports_failures_without_logging_reply_text(monkeypatch, capsys, failure):
    probe = runpy.run_path(str(PROBE))
    namespace = probe["main"].__globals__
    monkeypatch.setattr(settings, "llm_provider", "freellmapi")
    answers = {question: expected for _, question, expected in probe["CASES"]}

    class Provider:
        async def generate(self, request):
            if failure == "provider-error":
                raise RuntimeError("PRIVATE_TEST_MARKER")
            if failure == "wrong-answer":
                return SimpleNamespace(content="PRIVATE_TEST_MARKER")
            expected = answers[request.messages[-1]["content"]]
            return SimpleNamespace(content="masculina, grave e serena" if isinstance(expected, tuple) else expected)

    monkeypatch.setitem(namespace, "build_model_router", lambda: SimpleNamespace(
        registry=SimpleNamespace(get=lambda _: Provider())))
    assert await probe["main"]() == (1 if failure else 0)
    output = capsys.readouterr().out
    assert "PRIVATE_TEST_MARKER" not in output
    summary = json.loads(output.splitlines()[-1])
    assert summary["passed"] == (0 if failure else 12)
    assert summary["failed"] == (12 if failure else 0)
