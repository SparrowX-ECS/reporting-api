from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field, ValidationError


class Settings(BaseModel):
    customer_api_url: str = Field(default="http://localhost:8001")
    task_api_url: str = Field(default="http://localhost:8002")
    billing_api_url: str = Field(default="http://localhost:8003")
    upstream_timeout_seconds: float = Field(default=5.0, gt=0, le=60)

    @classmethod
    def from_environment(cls) -> Settings:
        values = {
            "customer_api_url": os.getenv("CUSTOMER_API_URL", "http://localhost:8001").rstrip("/"),
            "task_api_url": os.getenv("TASK_API_URL", "http://localhost:8002").rstrip("/"),
            "billing_api_url": os.getenv("BILLING_API_URL", "http://localhost:8003").rstrip("/"),
        }
        timeout = os.getenv("UPSTREAM_TIMEOUT_SECONDS")
        if timeout is not None:
            values["upstream_timeout_seconds"] = timeout
        return cls.model_validate(values)


class CustomerReport(BaseModel):
    customers: int = Field(ge=0, description="Total number of customers")


class TaskReport(BaseModel):
    open_tasks: int = Field(ge=0, description="Tasks in TODO or IN_PROGRESS state")


class BillingReport(BaseModel):
    pending_invoices: int = Field(ge=0, description="Invoices currently in PENDING state")


class SummaryReport(CustomerReport, TaskReport, BillingReport):
    """Overall operational summary assembled from all three upstream APIs."""


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
report_requests_total = Counter(
    "reporting_api_report_requests_total",
    "Report endpoint requests by report type",
    ("report",),
)


def _metric_path(path: str) -> str:
    return path if not path.startswith("/reports/") else path


def _list_payload(response: httpx.Response, service: str) -> list[dict[str, Any]]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"{service} API returned invalid JSON") from exc
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise HTTPException(status_code=502, detail=f"{service} API returned an invalid list response")
    return payload


async def fetch_list(client: httpx.AsyncClient, base_url: str, path: str, service: str) -> list[dict[str, Any]]:
    try:
        response = await client.get(f"{base_url}{path}")
        if response.is_error:
            request = response.request or httpx.Request("GET", f"{base_url}{path}")
            raise httpx.HTTPStatusError("Upstream API returned an error", request=request, response=response)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail=f"{service} API request timed out") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"{service} API returned HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"{service} API is unavailable") from exc
    return _list_payload(response, service)


def count_open_tasks(tasks: list[dict[str, Any]]) -> int:
    return sum(task.get("status") in {"TODO", "IN_PROGRESS"} for task in tasks)


def count_pending_invoices(invoices: list[dict[str, Any]]) -> int:
    return sum(invoice.get("status") == "PENDING" for invoice in invoices)


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

    app = FastAPI(
        title="SparrowX Labs Reporting API",
        version="1.0.0",
        description="Read-only operational reports owned by Noah Taylor, Analytics Team.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:8080,http://localhost:3000").split(","),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = app_settings
    app.state.http_client = managed_client

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)
        started = perf_counter()
        response = await call_next(request)
        path = _metric_path(request.url.path)
        http_requests_total.labels(request.method, path, str(response.status_code)).inc()
        http_request_duration_seconds.labels(request.method, path).observe(perf_counter() - started)
        return response

    @app.get("/health", tags=["system"], summary="Health check")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    async def customer_report() -> CustomerReport:
        report_requests_total.labels("customers").inc()
        customers = await fetch_list(app.state.http_client, app_settings.customer_api_url, "/customers", "Customer")
        return CustomerReport(customers=len(customers))

    async def task_report() -> TaskReport:
        report_requests_total.labels("tasks").inc()
        tasks = await fetch_list(app.state.http_client, app_settings.task_api_url, "/tasks", "Task")
        return TaskReport(open_tasks=count_open_tasks(tasks))

    async def billing_report() -> BillingReport:
        report_requests_total.labels("billing").inc()
        invoices = await fetch_list(app.state.http_client, app_settings.billing_api_url, "/invoices", "Billing")
        return BillingReport(pending_invoices=count_pending_invoices(invoices))

    @app.get(
        "/reports/customers",
        response_model=CustomerReport,
        tags=["reports"],
        summary="Customer statistics",
        responses={502: {"description": "Customer API failure"}, 504: {"description": "Customer API timeout"}},
    )
    async def customers_report() -> CustomerReport:
        return await customer_report()

    @app.get(
        "/reports/tasks",
        response_model=TaskReport,
        tags=["reports"],
        summary="Task statistics",
        responses={502: {"description": "Task API failure"}, 504: {"description": "Task API timeout"}},
    )
    async def tasks_report() -> TaskReport:
        return await task_report()

    @app.get(
        "/reports/billing",
        response_model=BillingReport,
        tags=["reports"],
        summary="Billing statistics",
        responses={502: {"description": "Billing API failure"}, 504: {"description": "Billing API timeout"}},
    )
    async def billing_reports() -> BillingReport:
        return await billing_report()

    @app.get(
        "/reports/summary",
        response_model=SummaryReport,
        tags=["reports"],
        summary="Overall operational summary",
        responses={502: {"description": "An upstream API failure"}, 504: {"description": "An upstream API timeout"}},
    )
    async def summary_report() -> SummaryReport:
        report_requests_total.labels("summary").inc()
        try:
            customer, tasks, billing = await asyncio.gather(customer_report(), task_report(), billing_report())
        except (ValidationError, TypeError) as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Upstream API returned invalid data") from exc
        return SummaryReport(
            customers=customer.customers,
            open_tasks=tasks.open_tasks,
            pending_invoices=billing.pending_invoices,
        )

    return app


app = create_app()
