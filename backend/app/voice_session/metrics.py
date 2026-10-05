from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class VoiceTurnMetrics:
    session_id: str
    turn_id: int
    clock: Callable[[], float] = time.monotonic
    timestamps: dict[str, float] = field(default_factory=dict)
    provider_selected: str | None = None
    fallback_reason: str | None = None

    def mark(self, stage: str) -> None:
        if stage:
            self.timestamps.setdefault(stage, self.clock())

    def _elapsed_ms(self, start: str, end: str) -> int | None:
        before = self.timestamps.get(start)
        after = self.timestamps.get(end)
        if before is None or after is None or after < before:
            return None
        return round((after - before) * 1000)

    def payload(self) -> dict[str, object]:
        latency_ms = {
            "transcript_to_first_token": self._elapsed_ms(
                "transcript_committed",
                "first_model_token",
            ),
            "first_token_to_audio": self._elapsed_ms(
                "first_model_token",
                "first_audio_chunk",
            ),
            "turn_total": self._elapsed_ms(
                "transcript_committed",
                "completed",
            ),
        }
        from app.observability.telemetry import record_voice_latency
        record_voice_latency(latency_ms)
        return {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "provider_selected": self.provider_selected,
            "fallback_reason": self.fallback_reason,
            "latency_ms": {
                name: value
                for name, value in latency_ms.items()
                if value is not None
            },
            "stages": sorted(self.timestamps),
        }
