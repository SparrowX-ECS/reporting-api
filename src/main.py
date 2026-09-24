import os
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from src.config import Settings
from src.routes.reports import create_router


http_requests_total = Counter(
    "reporting_api_http_requests_total",
    "Total HTTP requests handled by the Reporting API",
    ("method", "path", "status"),
)
http_request_duration_seconds = Histogram(
    "reporting_api_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ("method", "path"),
)


def create_app(settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> FastAPI:
    app_settings = settings or Settings.from_environment()
    managed_client = client or httpx.AsyncClient(timeout=app_settings.upstream_timeout_seconds)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        owns_client = client is None
        application.state.http_client = managed_client
        yield
        if owns_client:
            await managed_client.aclose()

    application = FastAPI(
        title="SparrowX Labs Reporting API",
        version="1.0.0",
        description="Read-only operational reports owned by the Analytics Team.",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:8080,http://localhost:3000").split(","),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.state.settings = app_settings

    @application.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)
        started = time.perf_counter()
        response = await call_next(request)
        http_requests_total.labels(request.method, request.url.path, str(response.status_code)).inc()
        http_request_duration_seconds.labels(request.method, request.url.path).observe(time.perf_counter() - started)
        return response

    @application.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/api/reporting/health", tags=["system"])
    async def api_health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    application.include_router(create_router(app_settings, managed_client))
    return application


app = create_app()
