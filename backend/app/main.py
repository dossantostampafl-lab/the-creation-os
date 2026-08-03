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

# Lote: CORS por ambiente + rate limiting no login. allow_origins=["*"] was
# hardcoded and unconditional before this — combined with
# allow_credentials=True, that's a known anti-pattern (browsers themselves
# refuse to honor credentials against a literal wildcard, but the *declared*
# server policy was still wrong, and unvalidated against environment). The
# origin list now comes from settings.cors_allowed_origins_list
# (app/config.py): required and validated non-empty in production, with a
# Python-level default covering the real local frontend dev origin
# (frontend/vite.config.ts, port 5173) everywhere else.
# resolve_cors_middleware_kwargs (app/config.py) is the one place deciding
# allow_credentials — never True alongside a literal "*", even if an
# operator explicitly configures that combination.
_cors_kwargs = resolve_cors_middleware_kwargs(settings.cors_allowed_origins_list)
if not _cors_kwargs["allow_credentials"]:
    logger.warning(
        "CORS_ALLOWED_ORIGINS includes '*' — disabling allow_credentials to avoid the "
        "wildcard-origin + credentials combination. Set explicit origins to allow credentialed requests."
    )

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
    """Lote: logging JSON estruturado + métricas de observabilidade.
    Replaces the old add_correlation_id, which only echoed back whatever
    the client sent (empty string if nothing) — never the UUID it would
    generate internally when the header was absent, so a caller with no
    correlation_id of their own had no way to learn what one was used
    (achado da auditoria anterior). This resolves/generates it once, here,
    and does three things with that single value: (1) sets it as this
    request's logging context (app.observability.logging) so every
    structured log emitted anywhere during the request — including deep in
    a service with no access to the Request object — carries it
    automatically; (2) records the request in the in-memory HTTP
    metrics counters Pulse now reports; (3) actually returns it in the
    X-Correlation-ID response header, real UUID or not.
    """
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
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
    # Auditoria: seção 3 (autenticação, Chronicles/verify, segurança mínima,
    # observabilidade). Nenhum destes existia antes desta auditoria. Escolha
    # deliberadamente restrita a headers que não dependem de conhecer a
    # origem/domínio real de produção nem o TLS termination setup:
    # - Strict-Transport-Security fica de fora: o stack roda em HTTP puro em
    #   dev/docker-compose hoje (sem TLS termination configurado); um browser
    #   que armazenasse esse header localmente passaria a forçar HTTPS nesse
    #   host, quebrando o acesso dev/local.
    # - Content-Security-Policy fica de fora: uma política errada quebra o
    #   frontend real; exige saber exatamente quais origens/scripts/estilos
    #   ele carrega, informação que esta auditoria não tem — reportado
    #   separadamente, não implementado às cegas.
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
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
