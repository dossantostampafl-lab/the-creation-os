from __future__ import annotations

import base64
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.inference.contracts import InferenceRequest
from app.voice_session.inference import StreamingProvider, stream_with_fallback
from app.voice_session.stt import STTTranscript

_WAKE_WORD = re.compile(r"\bdeus\b", re.IGNORECASE)
_WAKE_SEPARATORS = " \t\r\n,.;:!?-–—"


class RealtimeSTT(Protocol):
    async def send_audio(self, audio: bytes, *, commit: bool = False) -> None: ...

    async def receive_transcript(self) -> STTTranscript: ...


class RealtimeTTS(Protocol):
    async def send_text(self, text: str) -> None: ...

    async def finish(self) -> None: ...

    async def receive_audio(self) -> bytes | None: ...


class SessionState(StrEnum):
    ARMED = "ARMED"
    WAKE_DETECTED = "WAKE_DETECTED"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    RECOVERING = "RECOVERING"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class TranscriptDecision:
    wake_detected: bool = False
    acknowledge: bool = False
    command: str | None = None
    turn_id: int | None = None


class VoiceSession:
    def __init__(self, session_id: str) -> None:
        if not session_id:
            raise ValueError("session_id is required")
        self.session_id = session_id
        self.state = SessionState.ARMED
        self.turn_id = 0
        self._awake = False
        self._wake_acknowledged = False

    def _start_turn(
        self,
        command: str,
        *,
        wake_detected: bool = False,
        acknowledge: bool = False,
    ) -> TranscriptDecision:
        text = command.strip()
        if not text:
            return TranscriptDecision(wake_detected=wake_detected, acknowledge=acknowledge)
        self.turn_id += 1
        self.state = SessionState.THINKING
        return TranscriptDecision(
            wake_detected=wake_detected,
            acknowledge=acknowledge,
            command=text,
            turn_id=self.turn_id,
        )

    def on_transcript(self, transcript: STTTranscript) -> TranscriptDecision:
        text = transcript.text.strip()
        if not text or self.state not in {SessionState.ARMED, SessionState.WAKE_DETECTED, SessionState.LISTENING}:
            return TranscriptDecision()

        if not self._awake:
            match = _WAKE_WORD.search(text)
            if match is None:
                return TranscriptDecision()

            acknowledge = not self._wake_acknowledged
            if acknowledge:
                self._wake_acknowledged = True

            if not transcript.committed:
                self.state = SessionState.WAKE_DETECTED
                return TranscriptDecision(wake_detected=True, acknowledge=acknowledge)

            self._awake = True
            command = text[match.end():].lstrip(_WAKE_SEPARATORS)
            if command:
                return self._start_turn(
                    command,
                    wake_detected=True,
                    acknowledge=acknowledge,
                )
            self.state = SessionState.LISTENING
            return TranscriptDecision(wake_detected=True, acknowledge=acknowledge)

        if not transcript.committed:
            return TranscriptDecision()

        return self._start_turn(text)

    def mark_speaking(self, turn_id: int) -> bool:
        if turn_id != self.turn_id or self.state is not SessionState.THINKING:
            return False
        self.state = SessionState.SPEAKING
        return True

    def finish_speaking(self, turn_id: int) -> bool:
        if turn_id != self.turn_id or self.state is not SessionState.SPEAKING:
            return False
        self.state = SessionState.LISTENING
        return True

    def barge_in(self, turn_id: int) -> bool:
        if turn_id != self.turn_id or self.state is not SessionState.SPEAKING:
            return False
        self.state = SessionState.LISTENING
        return True

    def begin_recovery(self) -> None:
        if self.state is not SessionState.CLOSED:
            self.state = SessionState.RECOVERING

    def recovered(self) -> None:
        if self.state is SessionState.RECOVERING:
            self.state = SessionState.LISTENING if self._awake else SessionState.ARMED

    def close(self) -> None:
        self.state = SessionState.CLOSED


class VoiceSessionGateway:
    def __init__(
        self,
        *,
        session: VoiceSession,
        stt: RealtimeSTT,
        primary: StreamingProvider,
        fallback: StreamingProvider,
        tts: RealtimeTTS,
        first_token_timeout_seconds: float = 2.5,
    ) -> None:
        self.session = session
        self.stt = stt
        self.primary = primary
        self.fallback = fallback
        self.tts = tts
        self.first_token_timeout_seconds = first_token_timeout_seconds

    async def send_audio(self, audio: bytes, *, commit: bool = False) -> None:
        await self.stt.send_audio(audio, commit=commit)

    async def process_next_transcript(self) -> AsyncIterator[dict[str, object]]:
        transcript = await self.stt.receive_transcript()
        decision = self.session.on_transcript(transcript)

        if decision.wake_detected:
            yield {
                "type": "wake_detected",
                "session_id": self.session.session_id,
                "turn_id": decision.turn_id if decision.turn_id is not None else self.session.turn_id,
                "acknowledge": decision.acknowledge,
            }

        if decision.command is None or decision.turn_id is None:
            if decision.wake_detected:
                yield {
                    "type": "state",
                    "session_id": self.session.session_id,
                    "turn_id": self.session.turn_id,
                    "state": self.session.state.value,
                }
            return

        turn_id = decision.turn_id
        yield {
            "type": "state",
            "session_id": self.session.session_id,
            "turn_id": turn_id,
            "state": SessionState.THINKING.value,
        }

        request = InferenceRequest(
            messages=[{"role": "user", "content": decision.command}],
            metadata={
                "voice_session_id": self.session.session_id,
                "turn_id": turn_id,
                "skip_health_probe": True,
            },
        )
        speaking = False

        async for chunk in stream_with_fallback(
            request,
            primary=self.primary,
            fallback=self.fallback,
            first_token_timeout_seconds=self.first_token_timeout_seconds,
        ):
            if turn_id != self.session.turn_id:
                return
            await self.tts.send_text(chunk.text)
            yield {
                "type": "text_delta",
                "session_id": self.session.session_id,
                "turn_id": turn_id,
                "provider": chunk.provider,
                "text": chunk.text,
            }

            audio = await self.tts.receive_audio()
            if audio:
                if not speaking:
                    speaking = self.session.mark_speaking(turn_id)
                yield {
                    "type": "audio_chunk",
                    "session_id": self.session.session_id,
                    "turn_id": turn_id,
                    "audio_base64": base64.b64encode(audio).decode("ascii"),
                }

        await self.tts.finish()
        while True:
            audio = await self.tts.receive_audio()
            if audio is None:
                break
            if turn_id != self.session.turn_id:
                return
            if not speaking:
                speaking = self.session.mark_speaking(turn_id)
            yield {
                "type": "audio_chunk",
                "session_id": self.session.session_id,
                "turn_id": turn_id,
                "audio_base64": base64.b64encode(audio).decode("ascii"),
            }

        if speaking:
            self.session.finish_speaking(turn_id)
        elif self.session.state is SessionState.THINKING:
            self.session.state = SessionState.LISTENING

        yield {
            "type": "state",
            "session_id": self.session.session_id,
            "turn_id": turn_id,
            "state": self.session.state.value,
        }
