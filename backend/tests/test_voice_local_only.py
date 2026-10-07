from pathlib import Path

import pytest

from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_fresh_install_boots_without_downloading_optional_speech_assets(monkeypatch):
    monkeypatch.delenv("DEUS_VOICE_SESSION_ENABLED", raising=False)
    settings = Settings(_env_file=None)
    assert settings.deus_voice_session_enabled is False


def test_project_has_no_retired_speech_provider():
    retired = 'eleven' + 'labs'
    paths = [ROOT / 'backend' / 'app', ROOT / 'frontend' / 'src', ROOT / 'deploy', ROOT / '.github', ROOT / 'docs', ROOT / '.devcontainer', ROOT / 'scripts']
    files = [ROOT / '.env.example', ROOT / 'README.md']
    for directory in paths:
        files.extend(p for p in directory.rglob('*') if p.is_file() and p.suffix in {'.py', '.ts', '.tsx', '.sh', '.md', '.yml'})
    assert [str(p.relative_to(ROOT)) for p in files if retired in p.read_text().lower()] == []


def test_voice_has_no_paid_provider_configuration():
    fields = Settings.__fields__
    assert 'deus_voice_fallback_provider' not in fields
    assert 'klaus_provider' not in fields
    assert 'deus_voice_engine' not in fields


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_startup_warms_local_audio_only_after_activation(monkeypatch, enabled):
    from app.api import voice_session
    from app.config import settings
    from app.main import app, lifespan

    calls = []

    class Cache:
        async def get(self):
            calls.append("warm")
            return b"audio"

    monkeypatch.setattr(settings, "deus_voice_session_enabled", enabled)
    monkeypatch.setattr(voice_session, "_voice_acknowledgement_cache", lambda: Cache())
    async with lifespan(app):
        assert calls == (["warm"] if enabled else [])


def test_local_voice_activation_preserves_or_restores_anthropic_reserve():
    script = (ROOT / "deploy" / "oracle" / "set-local-voice.sh").read_text(encoding="utf-8")
    assert 'env_set LLM_FALLBACK_PROVIDERS ""' not in script
    assert 'ANTHROPIC_API_KEY' in script
    assert 'ANTHROPIC_MODEL' in script
    assert 'fallback="anthropic"' in script


def test_local_voice_activation_keeps_a_chatgpt_provider():
    script = (ROOT / "deploy" / "oracle" / "set-local-voice.sh").read_text(encoding="utf-8")
    chatgpt_branch = script.split('if [ "$provider" = "chatgpt" ]; then', 1)[1].split("else", 1)[0]
    # Installing local speech must not move a ChatGPT-plan deployment back to FreeLLMAPI.
    assert "env_set LLM_PROVIDER" not in chatgpt_branch
    assert "env_set LLM_FALLBACK_PROVIDERS" not in chatgpt_branch
    assert "env_set DEUS_VOICE_PRIMARY_PROVIDER chatgpt" in chatgpt_branch
    assert "env_set DEUS_LOCAL_VOICE_SILENCE_MS 1000" in script
