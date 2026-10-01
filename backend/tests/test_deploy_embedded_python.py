"""Every Python embedded in a deploy script must at least compile.

set-voice.sh shipped with stray backslashes inside an f-string. It reached the server, wrote
.env, recreated the containers, and only then died on a SyntaxError -- leaving the run red after
it had already changed things. Nothing caught it, because the test's docker stub intercepted the
very call that would have run the code.

Compiling the source is cheap and does not need a container, a stub, or a server.
"""

from __future__ import annotations

import py_compile
import re
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY = REPO_ROOT / "deploy" / "oracle"

# python -c '...' up to the closing quote, and python - <<'PY' ... PY heredocs. The embedded
# code uses double quotes throughout, so the first unescaped ' closes the -c argument.
INLINE = re.compile(r"python3? -c '([^']*)'", re.DOTALL)
HEREDOC = re.compile(r"python3? - <<'PY'\n(.*?)\nPY\n", re.DOTALL)


def _blocks() -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    for script in sorted(DEPLOY.glob("*.sh")):
        text = script.read_text(encoding="utf-8")
        for pattern in (INLINE, HEREDOC):
            for index, code in enumerate(pattern.findall(text), start=1):
                if code.strip():
                    found.append((script.name, index, code))
    return found


def test_there_is_python_to_check() -> None:
    """A regex that matches nothing would make every assertion below vacuous."""
    assert len(_blocks()) >= 4, [b[:2] for b in _blocks()]


@pytest.mark.parametrize("name,index,code", _blocks(), ids=lambda v: v if isinstance(v, str) else None)
def test_embedded_python_compiles(name: str, index: int, code: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(code)
        path = handle.name
    try:
        py_compile.compile(path, doraise=True)
    except py_compile.PyCompileError as error:
        raise AssertionError(f"{name} block {index} does not compile:\n{error}") from error


@pytest.mark.parametrize("audio", [b"\x00\x01", b""])
def test_voice_setup_requires_audio_from_the_realtime_client(monkeypatch, capsys, audio):
    import httpx

    from app.voice_session import tts

    calls = []

    class FakeRealtimeTTS:
        def __init__(self, config):
            self.remaining = [audio, None]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def send_text(self, text):
            calls.append(text)

        async def finish(self):
            calls.append("finish")

        async def receive_audio(self):
            return self.remaining.pop(0)

    monkeypatch.setattr(tts, "ElevenLabsRealtimeTTS", FakeRealtimeTTS)
    # Voice-name permission is optional; synthesis must still be exercised.
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: httpx.Response(401))
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "test-voice")
    code = next(code for name, _, code in _blocks() if name == "set-voice.sh")
    if audio:
        exec(compile(code, "set-voice.sh", "exec"), {})
        assert "Realtime speaking: 2 bytes" in capsys.readouterr().out
    else:
        with pytest.raises(SystemExit, match="Realtime voice failed"):
            exec(compile(code, "set-voice.sh", "exec"), {})
    assert calls == ["Estou aqui.", "finish"]
