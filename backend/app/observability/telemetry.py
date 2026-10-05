"""Bounded opt-in telemetry: export operational metadata, never conversations."""
from __future__ import annotations

import inspect
import json
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any

from loguru import logger
from opentelemetry import metrics, trace
from opentelemetry.metrics import Observation
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import SpanContext, Status, StatusCode, TraceState

_ENABLED = False
_INITIALIZED = False
_TRACER = trace.get_tracer(__name__)
_METER = metrics.get_meter(__name__)
_DURATION = _METER.create_histogram('creation.operation.duration', unit='s')
_COUNT = _METER.create_counter('creation.operation.count')
_ALLOWED = frozenset({'http.route', 'http.request.method', 'http.method',
    'http.response.status_code', 'http.status_code', 'server.address', 'server.port',
    'creation.operation', 'creation.provider', 'creation.stage', 'creation.outcome',
    'creation.error_type', 'creation.worker', 'service.name', 'service.namespace',
    'deployment.environment', 'telemetry.sdk.name', 'telemetry.sdk.language', 'telemetry.sdk.version'})


def safe_attributes(attributes: Any) -> dict[str, Any]:
    return {k: v for k, v in (attributes or {}).items() if k in _ALLOWED
            and isinstance(v, (str, int, float, bool)) and (not isinstance(v, str) or len(v) <= 160)}


def _context(ctx: SpanContext | None) -> SpanContext | None:
    return None if ctx is None else SpanContext(ctx.trace_id, ctx.span_id,
                                               ctx.is_remote, ctx.trace_flags, TraceState())


class SanitizingSpanExporter(SpanExporter):
    def __init__(self, delegate: SpanExporter):
        self.delegate = delegate

    def export(self, spans: Any) -> SpanExportResult:
        clean = [ReadableSpan(
            name=safe_attributes(s.attributes).get('creation.operation', 'http.request'),
            context=_context(s.context), parent=_context(s.parent),
            resource=Resource(safe_attributes(s.resource.attributes)),
            attributes=safe_attributes(s.attributes), events=(), links=(), kind=s.kind,
            status=Status(s.status.status_code), start_time=s.start_time, end_time=s.end_time,
        ) for s in spans]
        try:
            return self.delegate.export(clean)
        except Exception:
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        self.delegate.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.delegate.force_flush(timeout_millis)


@contextmanager
def operation(name: str, attributes: dict[str, Any] | None = None):
    if not _ENABLED:
        yield
        return
    started, outcome, error_type = time.monotonic(), 'ok', ''
    attrs = safe_attributes({'creation.operation': name, **(attributes or {})})
    with _TRACER.start_as_current_span(name, attributes=attrs,
            record_exception=False, set_status_on_exception=False) as span:
        try:
            yield
        except BaseException as exc:
            outcome = 'cancelled' if type(exc).__name__ == 'CancelledError' else 'error'
            error_type = type(exc).__name__
            span.set_status(Status(StatusCode.ERROR))
            span.set_attribute('creation.error_type', error_type)
            raise
        finally:
            span.set_attribute('creation.outcome', outcome)
            duration = time.monotonic() - started
            labels = {'operation': name, 'outcome': outcome}
            if 'creation.provider' in attrs:
                labels['provider'] = attrs['creation.provider']
            try:
                _DURATION.record(duration, labels)
                _COUNT.add(1, labels)
                ctx = span.get_span_context()
                logger.info(json.dumps({'telemetry_version': 1, 'operation': name,
                    'outcome': outcome, 'error_type': error_type,
                    'duration_seconds': round(duration, 6),
                    'trace_id': format(ctx.trace_id, '032x'),
                    'span_id': format(ctx.span_id, '016x')}, separators=(',', ':')))
            except Exception:
                pass


def traced(name: str):
    def decorate(function: Any) -> Any:
        if inspect.isasyncgenfunction(function):
            @wraps(function)
            async def generator(*args: Any, **kwargs: Any):
                iterator = function(*args, **kwargs)
                try:
                    while True:
                        # Never hold a ContextVar token across yields to another task.
                        with operation(name):
                            try:
                                item = await anext(iterator)
                            except StopAsyncIteration:
                                return
                        yield item
                finally:
                    await iterator.aclose()
            return generator
        if inspect.iscoroutinefunction(function):
            @wraps(function)
            async def asynchronous(*args: Any, **kwargs: Any):
                with operation(name):
                    return await function(*args, **kwargs)
            return asynchronous
        @wraps(function)
        def synchronous(*args: Any, **kwargs: Any):
            with operation(name):
                return function(*args, **kwargs)
        return synchronous
    return decorate


def configure_telemetry(service: str, fastapi_app: Any = None) -> bool:
    global _ENABLED, _INITIALIZED, _TRACER, _METER, _DURATION, _COUNT
    from app.config import settings
    if _INITIALIZED or not settings.telemetry_enabled:
        return _ENABLED
    _INITIALIZED = True
    try:
        import resource as process_resource

        from opentelemetry.exporter.http.transport._urllib3 import Urllib3HTTPTransport
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.propagate import set_global_textmap
        from opentelemetry.sdk.metrics import Histogram, MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
        resource = Resource({'service.name': 'creation-' + service,
                             'service.namespace': 'creation-os',
                             'deployment.environment': settings.app_env})
        endpoint = settings.telemetry_otlp_endpoint.rstrip('/')
        provider = TracerProvider(resource=resource,
            sampler=ParentBased(TraceIdRatioBased(settings.telemetry_sample_ratio)))
        provider.add_span_processor(BatchSpanProcessor(SanitizingSpanExporter(
            OTLPSpanExporter(endpoint=endpoint + '/v1/traces', timeout=2, _transport=Urllib3HTTPTransport())),
            max_queue_size=1024, max_export_batch_size=128, schedule_delay_millis=1000))
        trace.set_tracer_provider(provider)
        metrics.set_meter_provider(MeterProvider(resource=resource, views=[
            View(instrument_name="creation.*", instrument_type=Histogram, aggregation=ExplicitBucketHistogramAggregation(
                boundaries=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 45, 90)))
        ], metric_readers=[
            PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint + '/v1/metrics', timeout=2, _transport=Urllib3HTTPTransport()),
                export_interval_millis=15000, export_timeout_millis=2500)]))
        set_global_textmap(TraceContextTextMapPropagator())
        _TRACER, _METER = trace.get_tracer(__name__), metrics.get_meter(__name__)
        _DURATION = _METER.create_histogram('creation.operation.duration', unit='s')
        _COUNT = _METER.create_counter('creation.operation.count')
        started = time.monotonic()
        _METER.create_observable_gauge("creation.worker.alive", callbacks=[lambda _: [Observation(1)]])
        _METER.create_observable_gauge("creation.process.uptime", unit="s",
            callbacks=[lambda _: [Observation(time.monotonic() - started)]])
        _METER.create_observable_gauge("creation.process.memory.peak", unit="By",
            callbacks=[lambda _: [Observation(process_resource.getrusage(process_resource.RUSAGE_SELF).ru_maxrss * 1024)]])
        HTTPXClientInstrumentor().instrument()
        if fastapi_app is not None:
            FastAPIInstrumentor.instrument_app(fastapi_app, excluded_urls='.*health/(live|ready).*', exclude_spans=['receive', 'send'],
                http_capture_headers_server_request=[], http_capture_headers_server_response=[])
        _ENABLED = True
    except Exception as exc:
        logger.warning('telemetry initialization failed: {}', type(exc).__name__)
    return _ENABLED


def record_voice_latency(latency_ms: dict[str, int | None]) -> None:
    if not _ENABLED:
        return
    try:
        histogram = _METER.create_histogram("creation.voice.latency", unit="s")
        for stage, duration in latency_ms.items():
            if duration is not None:
                histogram.record(duration / 1000, {"stage": stage})
    except Exception:
        pass
