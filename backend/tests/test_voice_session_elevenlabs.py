from __future__ import annotations

import base64
from urllib.parse import parse_qs, urlparse

from app.voice_session.stt import (
    ElevenLabsSTTConfig,
    STTTranscript,
    encode_audio_chunk,
    parse_stt_event,
)
from app.voice_session.tts import (
    ElevenLabsTTSConfig,
    encode_tts_close,
    encode_tts_initialize,
    encode_tts_text,
    parse_tts_event,
)


def test_stt_config_uses_realtime_scribe_pcm_vad_and_portuguese():
    config = ElevenLabsSTTConfig(api_key="secret-value")
    parsed = urlparse(config.url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "wss"
    assert parsed.netloc == "api.elevenlabs.io"
    assert parsed.path == "/v1/speech-to-text/realtime"
    assert query["model_id"] == ["scribe_v2_realtime"]
    assert query["audio_format"] == ["pcm_16000"]
    assert query["language_code"] == ["pt"]
    assert query["commit_strategy"] == ["vad"]
    assert config.headers == {"xi-api-key": "secret-value"}


def test_stt_audio_chunk_uses_base64_and_never_contains_api_key():
    message = encode_audio_chunk(b"\x01\x02", commit=True)

    assert message == {
        "message_type": "input_audio_chunk",
        "audio_base_64": base64.b64encode(b"\x01\x02").decode("ascii"),
        "commit": True,
    }
    assert "key" not in repr(message).lower()


def test_stt_parser_distinguishes_partial_and_committed_transcripts():
    partial = parse_stt_event('{"message_type":"partial_transcript","text":"De"}')
    committed = parse_stt_event('{"message_type":"committed_transcript","text":"Deus"}')

    assert partial == STTTranscript(text="De", committed=False)
    assert committed == STTTranscript(text="Deus", committed=True)


def test_tts_config_uses_stream_input_existing_voice_and_portuguese():
    config = ElevenLabsTTSConfig(
        api_key="secret-value",
        voice_id="voice-123",
        model_id="eleven_flash_v2_5",
    )
    parsed = urlparse(config.url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "wss"
    assert parsed.netloc == "api.elevenlabs.io"
    assert parsed.path == "/v1/text-to-speech/voice-123/stream-input"
    assert query["model_id"] == ["eleven_flash_v2_5"]
    assert query["language_code"] == ["pt"]
    assert query["output_format"] == ["pcm_24000"]
    assert config.headers == {"xi-api-key": "secret-value"}


def test_tts_messages_stream_text_without_exposing_api_key():
    initialize = encode_tts_initialize()
    text = encode_tts_text("Olá ")
    close = encode_tts_close()

    assert initialize["text"] == " "
    assert text == {"text": "Olá ", "try_trigger_generation": True}
    assert close == {"text": ""}
    assert "key" not in repr((initialize, text, close)).lower()


def test_tts_parser_decodes_audio_and_recognizes_final_event():
    audio = parse_tts_event(
        '{"audio":"' + base64.b64encode(b"audio").decode("ascii") + '","is_final":false}'
    )
    final = parse_tts_event('{"is_final":true}')

    assert audio == b"audio"
    assert final is None
