from app.config import settings


def test_voice_runtime_uses_only_the_free_primary():
    assert settings.deus_voice_primary_provider == "freellmapi"
    assert settings.deus_voice_first_token_timeout_ms == 2500
