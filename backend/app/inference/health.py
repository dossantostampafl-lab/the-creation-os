from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class _CircuitRecord:
    state: CircuitState = CircuitState.CLOSED
    failures: int = 0
    opened_at: float | None = None


class ProviderCircuitBreaker:
    def __init__(self, *, failure_threshold: int = 3, cooldown_seconds: float = 30.0) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be >= 0")
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._records: dict[str, _CircuitRecord] = {}

    def _record(self, provider: str) -> _CircuitRecord:
        return self._records.setdefault(provider, _CircuitRecord())

    def state(self, provider: str) -> CircuitState:
        return self._record(provider).state

    def can_attempt(self, provider: str, *, now: float) -> bool:
        record = self._record(provider)
        if record.state is CircuitState.CLOSED:
            return True
        if record.state is CircuitState.HALF_OPEN:
            return False
        if record.opened_at is None:
            return False
        if now - record.opened_at >= self._cooldown_seconds:
            record.state = CircuitState.HALF_OPEN
            return True
        return False

    def record_success(self, provider: str) -> None:
        record = self._record(provider)
        record.state = CircuitState.CLOSED
        record.failures = 0
        record.opened_at = None

    def record_transient_failure(self, provider: str, *, now: float) -> None:
        record = self._record(provider)
        if record.state is CircuitState.HALF_OPEN:
            record.state = CircuitState.OPEN
            record.failures = self._failure_threshold
            record.opened_at = now
            return

        record.failures += 1
        if record.failures >= self._failure_threshold:
            record.state = CircuitState.OPEN
            record.opened_at = now


class ProviderRateLimitCooldown:
    def __init__(self) -> None:
        self._blocked_until: dict[str, float] = {}

    def register(self, provider: str, *, now: float, retry_after_seconds: float) -> None:
        if retry_after_seconds < 0:
            raise ValueError("retry_after_seconds must be >= 0")
        blocked_until = now + retry_after_seconds
        current = self._blocked_until.get(provider)
        if current is None or blocked_until > current:
            self._blocked_until[provider] = blocked_until

    def can_attempt(self, provider: str, *, now: float) -> bool:
        blocked_until = self._blocked_until.get(provider)
        if blocked_until is None:
            return True
        if now >= blocked_until:
            self._blocked_until.pop(provider, None)
            return True
        return False
