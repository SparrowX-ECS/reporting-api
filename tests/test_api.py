import asyncio

import httpx
import pytest

from src.config import Settings
from src.main import create_app


class MockUpstream:
    def __init__(self, responses=None, error=None):
        self.responses = responses or {}
        self.error = error
        self.calls = []

    async def get(self, url):
        self.calls.append(url)
        if self.error:
            raise self.error
        key = "customers" if "customer" in url else "tasks" if "task" in url else "invoices"
        return httpx.Response(200, json=self.responses[key])

    async def aclose(self):
        pass


@pytest.fixture
def settings():
    return Settings(customer_api_url="http://customer", task_api_url="http://task", billing_api_url="http://billing")


def request(app, method, path, **kwargs):
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(check())


def test_health_docs_openapi_and_metrics_are_local_only(settings):
    app = create_app(settings, MockUpstream())
    assert request(app, "GET", "/health").json() == {"status": "ok"}
    assert request(app, "GET", "/docs").status_code == 200
    assert request(app, "GET", "/openapi.json").status_code == 200
    assert request(app, "GET", "/metrics").status_code == 200


def test_each_report_endpoint_and_summary(settings):
    upstream = MockUpstream({
        "customers": [{"id": 1}, {"id": 2}],
        "tasks": [{"status": "TODO"}, {"status": "DONE"}, {"status": "IN_PROGRESS"}],
        "invoices": [{"status": "PENDING"}, {"status": "PAID"}],
    })
    app = create_app(settings, upstream)
    assert request(app, "GET", "/api/reporting/customers").json() == {"customers": 2}
    assert request(app, "GET", "/api/reporting/tasks").json() == {"open_tasks": 2}
    assert request(app, "GET", "/api/reporting/billing").json() == {"pending_invoices": 1}
    assert request(app, "GET", "/api/reporting/summary").json() == {"customers": 2, "open_tasks": 2, "pending_invoices": 1}
    assert set(upstream.calls) == {"http://customer/api/customer/", "http://task/api/task/", "http://billing/api/billing/"}


def test_upstream_timeout_returns_504(settings):
    app = create_app(settings, MockUpstream(error=httpx.ReadTimeout("timed out")))
    response = request(app, "GET", "/api/reporting/customers")
    assert response.status_code == 504
    assert response.json()["detail"] == "Customer API request timed out"


def test_upstream_http_error_and_invalid_payload_return_502(settings):
    class ErrorUpstream(MockUpstream):
        async def get(self, url):
            request = httpx.Request("GET", url)
            response = httpx.Response(503, request=request)
            raise httpx.HTTPStatusError("bad gateway", request=request, response=response)

    assert request(create_app(settings, ErrorUpstream()), "GET", "/api/reporting/tasks").status_code == 502
    assert request(create_app(settings, MockUpstream({"customers": {"count": 2}})), "GET", "/api/reporting/customers").status_code == 502


def test_unknown_path_is_not_found(settings):
    assert request(create_app(settings, MockUpstream()), "GET", "/api/reporting/unknown").status_code == 404
