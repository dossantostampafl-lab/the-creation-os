from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from loguru import logger as struct_logger

from app.admin.creator import restore_configured_creator
from app.admin.worker import restore_configured_worker
from app.api import router as api_router
from app.auth.routes import router as auth_router
from app.config import resolve_cors_middleware_kwargs, settings
from app.core.domain import AuthorizationDenied, DomainError
from app.observability.logging import configure_logging, reset_log_context, set_log_context
from app.observability.metrics import request_metrics
from app.services.domain import NotFoundError

logger = logging.getLogger("app.main")
configure_logging(level=settings.log_level)

app = FastAPI(title="The Creation OS", version="0.1.0")

_cors_kwargs = resolve_cors_middleware_kwargs(settings.cors_allowed_origins_list)
if not _cors_kwargs["allow_credentials"]:
    logger.warning("CORS wildcard configured; credentialed browser requests are disabled")

app.add_middleware(CORSMiddleware, **_cors_kwargs)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api/v1")


@app.on_event("startup")
async def ensure_development_creator() -> None:
    if settings.app_env == "development":
        await restore_configured_creator()


@app.on_event("startup")
async def ensure_development_worker() -> None:
    if settings.app_env == "development":
        await restore_configured_worker()


@app.middleware("http")
async def observe_request(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    set_log_context(correlation_id=correlation_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        latency_ms = (time.perf_counter() - start) * 1000
        request_metrics.record(status_code=500, latency_ms=latency_ms)
        struct_logger.bind(
            event="http_request_failed",
            correlation_id=correlation_id,
            aggregate_type="http_request",
            aggregate_id=request.url.path,
            method=request.method,
        ).exception("unhandled exception during request")
        reset_log_context()
        raise

    latency_ms = (time.perf_counter() - start) * 1000
    request_metrics.record(status_code=response.status_code, latency_ms=latency_ms)
    struct_logger.bind(
        event="http_request_completed",
        correlation_id=correlation_id,
        aggregate_type="http_request",
        aggregate_id=request.url.path,
        method=request.method,
        status_code=response.status_code,
        latency_ms=round(latency_ms, 2),
    ).info(f"{request.method} {request.url.path} -> {response.status_code}")
    response.headers["X-Correlation-ID"] = correlation_id
    reset_log_context()
    return response


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(DomainError)
async def domain_exception_handler(request: Request, exc: DomainError):
    code = 403 if isinstance(exc, AuthorizationDenied) else 409
    return JSONResponse(status_code=code, content={"detail": str(exc), "code": exc.__class__.__name__})


@app.exception_handler(NotFoundError)
async def not_found_exception_handler(request: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc), "code": "not_found"})


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    struct_logger.bind(
        path=request.url.path,
        method=request.method,
        correlation_id=getattr(request.state, "correlation_id", "missing"),
        error_type=exc.__class__.__name__,
    ).exception("unhandled server error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
