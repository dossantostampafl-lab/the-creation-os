from __future__ import annotations

import threading


class RequestMetrics:
    """In-memory, process-local HTTP request/latency counters. Lote: logging
    JSON estruturado + métricas de observabilidade. No external metrics
    infrastructure (Prometheus etc.) exists in this project yet — this is
    deliberately just process memory, matching what the lote prompt asks
    for ("não precisa de infraestrutura de métricas externa... a menos que
    já exista base"). Accurate for the real deployment topology today (one
    `api` process, no replicas — see docker-compose.yml)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total_requests = 0
        self._total_errors = 0
        self._total_latency_ms = 0.0

    def record(self, *, status_code: int, latency_ms: float) -> None:
        with self._lock:
            self._total_requests += 1
            if status_code >= 500:
                self._total_errors += 1
            self._total_latency_ms += latency_ms

    def snapshot(self) -> dict:
        with self._lock:
            average = (self._total_latency_ms / self._total_requests) if self._total_requests else 0.0
            return {
                "http_requests_total": self._total_requests,
                "http_errors_total": self._total_errors,
                "http_average_latency_ms": round(average, 2),
            }


request_metrics = RequestMetrics()
