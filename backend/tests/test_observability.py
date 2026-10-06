from __future__ import annotations


def test_exported_attributes_cannot_contain_private_payloads():
    from app.observability.telemetry import safe_attributes
    private = {'http.url': 'https://host/api?ticket=SECRET', 'prompt': 'PRIVATE',
               'exception.message': 'PRIVATE', 'http.request.header.authorization': 'Bearer SECRET',
               'http.route': '/api/v1/missions/{id}', 'http.request.method': 'GET',
               'http.response.status_code': 200, 'creation.operation': 'llm.attempt',
               'creation.provider': 'freellmapi', 'creation.model': 'model-fast',
               'creation.error_type': 'ReadTimeout'}
    clean = safe_attributes(private)
    assert 'PRIVATE' not in str(clean) and 'SECRET' not in str(clean)
    assert clean['http.route'] == '/api/v1/missions/{id}'
    assert clean['http.response.status_code'] == 200
    assert clean['creation.error_type'] == 'ReadTimeout'
    assert clean['creation.provider'] == 'freellmapi'
    assert clean['creation.model'] == 'model-fast'


def test_disabled_telemetry_preserves_application_result():
    from app.observability.telemetry import traced
    @traced('test.operation')
    def run(value):
        return value + 1
    assert run(4) == 5


def test_exporter_removes_names_events_resource_and_tracestate():
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import ReadableSpan
    from opentelemetry.sdk.trace.export import SpanExportResult
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import SpanContext, Status, StatusCode, TraceState

    from app.observability.telemetry import SanitizingSpanExporter
    target = InMemorySpanExporter()
    span = ReadableSpan('GET /private/SECRET',
        context=SpanContext(1, 2, False, trace_state=TraceState([('secret', 'PRIVATE')])),
        resource=Resource({'service.name': 'creation-api', 'private': 'PRIVATE'}),
        attributes={'http.url': 'https://host/SECRET', 'http.request.method': 'GET'},
        status=Status(StatusCode.ERROR, 'PRIVATE'), start_time=1, end_time=2)
    assert SanitizingSpanExporter(target).export([span]) == SpanExportResult.SUCCESS
    clean = target.get_finished_spans()[0]
    assert clean.name == 'http.request'
    assert clean.status.description is None
    assert not clean.context.trace_state
    assert not clean.events and not clean.links
    assert 'PRIVATE' not in str(clean.resource.attributes) + str(clean.attributes)
    assert 'SECRET' not in str(clean.attributes)


async def test_instrumentation_preserves_async_result_and_exception(monkeypatch):
    import pytest

    import app.observability.telemetry as telemetry
    monkeypatch.setattr(telemetry, '_ENABLED', True)
    @telemetry.traced('test.operation')
    async def fail():
        raise ValueError('PRIVATE')
    with pytest.raises(ValueError, match='PRIVATE'):
        await fail()
    @telemetry.traced('test.generator')
    async def stream():
        yield 1
        yield 2
    assert [item async for item in stream()] == [1, 2]


def test_exporter_outage_is_a_failure_result_not_an_application_exception():
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import ReadableSpan
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

    from app.observability.telemetry import SanitizingSpanExporter
    class Broken(SpanExporter):
        def export(self, spans):
            raise RuntimeError('network down')
    span = ReadableSpan('safe', resource=Resource({'service.name': 'test'}), start_time=1, end_time=2)
    assert SanitizingSpanExporter(Broken()).export([span]) == SpanExportResult.FAILURE


def test_snapshot_labels_have_bounded_values():
    from app.observability.state import _status
    assert _status(True) == 'active'
    assert _status(False) == 'paused'
    assert _status('FAILED') == 'failed'
    assert _status('PRIVATE_ARBITRARY_STATE') == 'other'


def test_enabled_sdk_initializes_without_optional_requests_and_does_not_wait_for_export():
    import os
    import subprocess
    import sys
    code = '''
import time
from app.observability.telemetry import configure_telemetry, operation
assert configure_telemetry('test-bootstrap')
started = time.monotonic()
with operation('test.operation'):
    result = 42
assert result == 42 and time.monotonic() - started < 0.25
'''
    env = {**os.environ, 'TELEMETRY_ENABLED': 'true',
           'TELEMETRY_OTLP_ENDPOINT': 'http://127.0.0.1:9'}
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_dashboard_panels_and_datasources_are_unambiguous():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / 'deploy/observability/grafana/dashboards'
    dashboards = [json.loads(path.read_text()) for path in root.glob('*.json')]
    assert len(dashboards) == 8
    assert len({dashboard['uid'] for dashboard in dashboards}) == 8
    for dashboard in dashboards:
        ids = [panel['id'] for panel in dashboard['panels']]
        assert len(ids) == len(set(ids)), dashboard['title']
        for panel in dashboard['panels']:
            assert panel['datasource']['uid'] in {'prometheus', 'loki', 'tempo'}
