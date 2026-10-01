from __future__ import annotations


class VoiceSynthesisError(RuntimeError):
    """Safe public error for local synthesis failures."""

    code = "VOICE_TTS_UNAVAILABLE"
    nonretryable = False

    def __init__(self) -> None:
        super().__init__("Não foi possível gerar o áudio local. Tente novamente.")
