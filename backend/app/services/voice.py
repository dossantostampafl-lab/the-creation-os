from __future__ import annotations

import uuid

import httpx

from app.config import settings
from app.core.domain import Actor, DomainError, require_creator
from app.repositories.domain import DomainRepository

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"


class VoiceSynthesisError(DomainError):
    pass


class VOICE_SYNTHESIS_DISABLED(VoiceSynthesisError):
    pass


class VOICE_SYNTHESIS_EMPTY_TEXT(VoiceSynthesisError):
    pass


class VOICE_SYNTHESIS_TEXT_TOO_LONG(VoiceSynthesisError):
    pass


class VOICE_PROVIDER_UNAVAILABLE(VoiceSynthesisError):
    pass


class VoiceTranscriptionError(DomainError):
    pass


class VOICE_TRANSCRIPTION_DISABLED(VoiceTranscriptionError):
    pass


class VOICE_TRANSCRIPTION_EMPTY_AUDIO(VoiceTranscriptionError):
    pass


class VOICE_TRANSCRIPTION_TOO_LARGE(VoiceTranscriptionError):
    pass


class VOICE_TRANSCRIPTION_UNAVAILABLE(VoiceTranscriptionError):
    pass


class VoiceSynthesisService:
    def __init__(self, repository: DomainRepository, client: httpx.AsyncClient | None = None) -> None:
        self.repository = repository
        self.client = client

    async def synthesize(self, actor: Actor, text: str, correlation_id: str) -> tuple[bytes, str]:
        require_creator(actor, "synthesize DEUS voice")
        normalized = " ".join(text.split())
        if not normalized:
            raise VOICE_SYNTHESIS_EMPTY_TEXT("Voice synthesis requires non-empty text")
        if len(normalized) > settings.voice_synthesis_max_chars:
            raise VOICE_SYNTHESIS_TEXT_TOO_LONG("Voice synthesis text exceeds configured limit")
        if not settings.elevenlabs_enabled:
            raise VOICE_SYNTHESIS_DISABLED("ElevenLabs voice synthesis is disabled")
        if settings.elevenlabs_api_key is None:
            raise VOICE_SYNTHESIS_DISABLED("ElevenLabs API key is not configured")

        event_id = str(uuid.uuid4())
        await self._record(
            "voice.synthesis.requested", event_id, actor, correlation_id,
            {"provider": "elevenlabs", "text_length": len(normalized), "voice_id": settings.elevenlabs_voice_id},
        )
        # Commit before calling the provider: add_event holds the global Chronicle lock
        # until commit, and a slow provider must not stall every other writer.
        try:
            audio, content_type = await self._call_elevenlabs(normalized)
        except Exception as exc:
            await self._record(
                "voice.synthesis.failed", event_id, actor, correlation_id,
                {"provider": "elevenlabs", "code": exc.__class__.__name__},
            )
            if isinstance(exc, VoiceSynthesisError):
                raise
            raise VOICE_PROVIDER_UNAVAILABLE("ElevenLabs voice provider is unavailable") from exc
        await self._record(
            "voice.synthesis.succeeded", event_id, actor, correlation_id,
            {"provider": "elevenlabs", "content_type": content_type, "audio_bytes": len(audio)},
        )
        return audio, content_type

    async def transcribe(
        self,
        actor: Actor,
        audio: bytes,
        content_type: str,
        correlation_id: str,
    ) -> tuple[str, str | None, float | None]:
        """Transcribe a short Creator utterance with Scribe; the browser remains the fail-open fallback."""
        require_creator(actor, "transcribe Creator voice")
        if not audio:
            raise VOICE_TRANSCRIPTION_EMPTY_AUDIO("Voice transcription requires audio")
        if len(audio) > settings.voice_transcription_max_bytes:
            raise VOICE_TRANSCRIPTION_TOO_LARGE("Voice transcription audio exceeds configured limit")
        if not settings.elevenlabs_enabled or settings.elevenlabs_api_key is None:
            raise VOICE_TRANSCRIPTION_DISABLED("ElevenLabs voice transcription is disabled")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if not media_type.startswith("audio/"):
            raise VOICE_TRANSCRIPTION_EMPTY_AUDIO("Voice transcription requires audio content")

        event_id = str(uuid.uuid4())
        await self._record(
            "voice.transcription.requested",
            event_id,
            actor,
            correlation_id,
            {"provider": "elevenlabs", "audio_bytes": len(audio), "content_type": media_type},
            aggregate_type="voice_transcription",
        )
        try:
            text, language_code, language_probability = await self._call_elevenlabs_stt(audio, media_type)
        except Exception as exc:
            await self._record(
                "voice.transcription.failed",
                event_id,
                actor,
                correlation_id,
                {"provider": "elevenlabs", "code": exc.__class__.__name__},
                aggregate_type="voice_transcription",
            )
            if isinstance(exc, VoiceTranscriptionError):
                raise
            raise VOICE_TRANSCRIPTION_UNAVAILABLE("ElevenLabs transcription provider is unavailable") from exc

        await self._record(
            "voice.transcription.succeeded",
            event_id,
            actor,
            correlation_id,
            {
                "provider": "elevenlabs",
                "text_length": len(text),
                "language_code": language_code,
                "language_probability": language_probability,
            },
            aggregate_type="voice_transcription",
        )
        return text, language_code, language_probability

    async def _record(
        self,
        event_type: str,
        event_id: str,
        actor: Actor,
        correlation_id: str,
        payload: dict,
        *,
        aggregate_type: str = "voice_synthesis",
    ) -> None:
        await self.repository.add_event(
            event_type, aggregate_type, event_id, actor.id, actor.role, correlation_id, payload,
        )
        await self.repository.commit()

    async def _call_elevenlabs(self, text: str) -> tuple[bytes, str]:
        timeout = httpx.Timeout(settings.elevenlabs_timeout_seconds)
        client = self.client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)
        close_client = self.client is None
        try:
            response = await client.post(
                ELEVENLABS_TTS_URL.format(voice_id=settings.elevenlabs_voice_id),
                params={"output_format": "mp3_22050_32"},
                headers={
                    "accept": "audio/mpeg",
                    "content-type": "application/json",
                    "xi-api-key": settings.elevenlabs_api_key.get_secret_value() if settings.elevenlabs_api_key else "",
                },
                json={
                    "text": text,
                    "model_id": settings.elevenlabs_model_id,
                    "voice_settings": {
                        "stability": 0.62,
                        "similarity_boost": 0.72,
                        "style": 0.08,
                        "use_speaker_boost": True,
                    },
                },
            )
            if response.status_code in {401, 403, 408, 409, 422, 429} or response.status_code >= 500:
                raise VOICE_PROVIDER_UNAVAILABLE(f"ElevenLabs rejected synthesis with HTTP {response.status_code}")
            response.raise_for_status()
            content_type = response.headers.get("content-type", "audio/mpeg").split(";")[0]
            if not content_type.startswith("audio/"):
                raise VOICE_PROVIDER_UNAVAILABLE("ElevenLabs returned non-audio content")
            if not response.content:
                raise VOICE_PROVIDER_UNAVAILABLE("ElevenLabs returned empty audio")
            return response.content, content_type
        except httpx.TimeoutException as exc:
            raise VOICE_PROVIDER_UNAVAILABLE("ElevenLabs voice provider timed out") from exc
        except httpx.HTTPError as exc:
            raise VOICE_PROVIDER_UNAVAILABLE("ElevenLabs voice provider failed") from exc
        finally:
            if close_client:
                await client.aclose()

    async def _call_elevenlabs_stt(
        self,
        audio: bytes,
        content_type: str,
    ) -> tuple[str, str | None, float | None]:
        timeout = httpx.Timeout(settings.elevenlabs_timeout_seconds)
        client = self.client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)
        close_client = self.client is None
        try:
            response = await client.post(
                ELEVENLABS_STT_URL,
                headers={
                    "accept": "application/json",
                    "xi-api-key": settings.elevenlabs_api_key.get_secret_value() if settings.elevenlabs_api_key else "",
                },
                files={"file": ("creator-utterance.webm", audio, content_type)},
                data={
                    "model_id": settings.elevenlabs_stt_model_id,
                    "language_code": "por",
                    "tag_audio_events": "false",
                    "diarize": "false",
                },
            )
            if response.status_code in {401, 403, 408, 409, 422, 429} or response.status_code >= 500:
                raise VOICE_TRANSCRIPTION_UNAVAILABLE(
                    f"ElevenLabs rejected transcription with HTTP {response.status_code}"
                )
            response.raise_for_status()
            payload = response.json()
            text = " ".join(str(payload.get("text", "")).split())
            if not text:
                raise VOICE_TRANSCRIPTION_UNAVAILABLE("ElevenLabs returned an empty transcript")
            language_code = payload.get("language_code")
            probability = payload.get("language_probability")
            return (
                text,
                str(language_code) if language_code else None,
                float(probability) if isinstance(probability, (int, float)) else None,
            )
        except httpx.TimeoutException as exc:
            raise VOICE_TRANSCRIPTION_UNAVAILABLE("ElevenLabs transcription provider timed out") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise VOICE_TRANSCRIPTION_UNAVAILABLE("ElevenLabs transcription provider failed") from exc
        finally:
            if close_client:
                await client.aclose()
