from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from loguru import logger

from app.api import router as api_router
from app.auth.routes import router as auth_router
from app.config import settings
from app.core.domain import AuthorizationDenied, DomainError
from app.services.domain import NotFoundError

app = FastAPI(title="The Creation OS", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api/v1")


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
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
    logger.bind(
        path=request.url.path,
        method=request.method,
        correlation_id=request.headers.get("X-Correlation-ID", "missing"),
        error_type=exc.__class__.__name__,
    ).exception("unhandled server error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
