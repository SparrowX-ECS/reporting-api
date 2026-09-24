import asyncio
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError
from prometheus_client import Counter

from src.config import Settings
from src.schemas import BillingReport, CustomerReport, SummaryReport, TaskReport


report_requests_total = Counter(
    "reporting_api_report_requests_total",
    "Report endpoint requests by report type",
    ("report",),
)


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


def create_router(settings: Settings, client: httpx.AsyncClient) -> APIRouter:
    router = APIRouter(prefix="/api/reporting", tags=["reports"])

    async def customer_report() -> CustomerReport:
        report_requests_total.labels("customers").inc()
        customers = await fetch_list(client, settings.customer_api_url, "/api/customer/", "Customer")
        return CustomerReport(customers=len(customers))

    async def task_report() -> TaskReport:
        report_requests_total.labels("tasks").inc()
        tasks = await fetch_list(client, settings.task_api_url, "/api/task/", "Task")
        return TaskReport(open_tasks=count_open_tasks(tasks))

    async def billing_report() -> BillingReport:
        report_requests_total.labels("billing").inc()
        invoices = await fetch_list(client, settings.billing_api_url, "/api/billing/", "Billing")
        return BillingReport(pending_invoices=count_pending_invoices(invoices))

    @router.get("/customers", response_model=CustomerReport)
    async def customers_report() -> CustomerReport:
        return await customer_report()

    @router.get("/tasks", response_model=TaskReport)
    async def tasks_report() -> TaskReport:
        return await task_report()

    @router.get("/billing", response_model=BillingReport)
    async def billing_report_endpoint() -> BillingReport:
        return await billing_report()

    @router.get("/summary", response_model=SummaryReport)
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

    return router
