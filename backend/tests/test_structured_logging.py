"""Lote: logging JSON estruturado + métricas de observabilidade (Parte A).
Confirms structured JSON logging is real application-wide behavior, not
just the one isolated app/observability/security.py call site: every
request emits a JSON log line with the fields the original v0.3 document
requires, correlation_id matches the actual request, and sensitive keys
never make it into the output even if a caller carelessly binds one.
"""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from loguru import logger

from app.main import app
from app.observability.logging import record_to_json

pytestmark = pytest.mark.integration

REQUIRED_FIELDS = ("timestamp", "level", "service", "event", "correlation_id", "actor_id", "aggregate_type", "aggregate_id", "message")


@pytest.fixture
def captured_logs():
    """Adds a second, in-memory loguru sink alongside the app's real stdout
    one (configure_logging(), called once at app.main import time) — loguru
    supports multiple simultaneous sinks natively, so this doesn't disturb
    the real one."""
    captured: list[str] = []
    sink_id = logger.add(lambda message: captured.append(record_to_json(message.record)), level="DEBUG")
    yield captured
    logger.remove(sink_id)


def _http_request_completed_entries(captured: list[str]) -> list[dict]:
    entries = [json.loads(line) for line in captured]
    return [entry for entry in entries if entry.get("event") == "http_request_completed"]


@pytest.mark.asyncio
async def test_request_log_has_required_fields_and_is_valid_json(captured_logs):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health/live")
    assert response.status_code == 200

    entries = _http_request_completed_entries(captured_logs)
    assert entries, captured_logs
    entry = entries[-1]
    for field in REQUIRED_FIELDS:
        assert field in entry, (field, entry)
    assert entry["service"] == "the-creation-os-api"
    assert entry["level"] == "INFO"
    assert entry["aggregate_type"] == "http_request"
    assert entry["aggregate_id"] == "/api/v1/health/live"


@pytest.mark.asyncio
async def test_log_correlation_id_matches_the_request_correlation_id(captured_logs):
    sent_correlation_id = str(uuid.uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health/live", headers={"X-Correlation-ID": sent_correlation_id})
    assert response.headers["X-Correlation-ID"] == sent_correlation_id

    entries = _http_request_completed_entries(captured_logs)
    assert entries[-1]["correlation_id"] == sent_correlation_id


@pytest.mark.asyncio
async def test_generated_correlation_id_is_echoed_and_logged_when_client_sends_none(captured_logs):
    """Lote: Parte C. add_correlation_id (now observe_request) used to only
    echo back what the client sent — empty string if nothing — so a caller
    with no correlation_id of its own had no way to learn what one was
    used internally. Must now return a real, usable value."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health/live")
    returned_correlation_id = response.headers["X-Correlation-ID"]
    assert returned_correlation_id
    uuid.UUID(returned_correlation_id)  # real UUID, not echoed garbage or empty

    entries = _http_request_completed_entries(captured_logs)
    assert entries[-1]["correlation_id"] == returned_correlation_id


def test_sensitive_keys_are_redacted_from_log_output():
    captured: list[str] = []
    sink_id = logger.add(lambda message: captured.append(record_to_json(message.record)), level="DEBUG")
    try:
        logger.bind(
            event="login_test", password="super-secret-value", token="abc-token-value", authorization="Bearer abc-token-value"
        ).warning("simulated login-adjacent log call")
    finally:
        logger.remove(sink_id)

    assert captured
    raw = captured[0]
    assert "super-secret-value" not in raw
    assert "abc-token-value" not in raw
    parsed = json.loads(raw)
    assert "password" not in parsed
    assert "token" not in parsed
    assert "authorization" not in parsed
    assert parsed["message"] == "simulated login-adjacent log call"
