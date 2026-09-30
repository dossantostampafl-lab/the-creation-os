from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from app.voice_session.stt import STTTranscript

_WAKE_WORD = re.compile(r"\bdeus\b", re.IGNORECASE)
_WAKE_SEPARATORS = " \t\r\n,.;:!?-–—"


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
