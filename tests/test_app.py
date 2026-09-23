import asyncio

import httpx
import pytest

from app import Settings, create_app


class MockUpstream:
    def __init__(self, responses=None, error=None):
        self.responses = responses or {}
        self.error = error
        self.calls = []

    async def get(self, url):
        self.calls.append(url)
        if self.error:
            raise self.error
        return httpx.Response(200, json=self.responses[url.rsplit("/", 1)[-1]])

    async def aclose(self):
        pass


@pytest.fixture
def settings():
    return Settings(customer_api_url="http://customer", task_api_url="http://task", billing_api_url="http://billing")


def test_health_docs_openapi_and_metrics_are_local_only(settings):
    app = create_app(settings, MockUpstream())
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/health")).json() == {"status": "ok"}
            assert (await client.get("/docs")).status_code == 200
            assert (await client.get("/openapi.json")).status_code == 200
            assert (await client.get("/metrics")).status_code == 200
    asyncio.run(check())


def test_each_report_endpoint_and_summary(settings):
    upstream = MockUpstream({
        "customers": [{"id": 1}, {"id": 2}],
        "tasks": [{"status": "TODO"}, {"status": "DONE"}, {"status": "IN_PROGRESS"}],
        "invoices": [{"status": "PENDING"}, {"status": "PAID"}],
    })
    app = create_app(settings, upstream)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/reports/customers")).json() == {"customers": 2}
            assert (await client.get("/reports/tasks")).json() == {"open_tasks": 2}
            assert (await client.get("/reports/billing")).json() == {"pending_invoices": 1}
            assert (await client.get("/reports/summary")).json() == {"customers": 2, "open_tasks": 2, "pending_invoices": 1}
    asyncio.run(check())
    assert set(upstream.calls) == {"http://customer/customers", "http://task/tasks", "http://billing/invoices"}


def test_upstream_timeout_returns_504(settings):
    upstream = MockUpstream(error=httpx.ReadTimeout("timed out"))
    app = create_app(settings, upstream)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.get("/reports/customers")
    response = asyncio.run(check())
    assert response.status_code == 504
    assert response.json()["detail"] == "Customer API request timed out"


def test_upstream_http_error_returns_502(settings):
    class ErrorUpstream(MockUpstream):
        async def get(self, url):
            request = httpx.Request("GET", url)
            response = httpx.Response(503, request=request)
            raise httpx.HTTPStatusError("bad gateway", request=request, response=response)

    app = create_app(settings, ErrorUpstream())
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.get("/reports/tasks")
    response = asyncio.run(check())
    assert response.status_code == 502


def test_invalid_upstream_payload_returns_502(settings):
    upstream = MockUpstream({"customers": {"count": 2}})
    app = create_app(settings, upstream)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.get("/reports/customers")
    response = asyncio.run(check())
    assert response.status_code == 502


def test_unknown_path_is_validation_error(settings):
    app = create_app(settings, MockUpstream())
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.get("/reports/unknown")
    assert asyncio.run(check()).status_code == 404
