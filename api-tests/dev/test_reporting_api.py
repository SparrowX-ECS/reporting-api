import os

import httpx


BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")


def client() -> httpx.Client:
    if not BASE_URL:
        raise RuntimeError("BASE_URL must point to the deployed reporting-api service")
    return httpx.Client(base_url=BASE_URL, timeout=20.0, follow_redirects=True)


def assert_non_negative_integer(value: object, field: str) -> None:
    assert isinstance(value, int), f"{field} must be an integer: {value!r}"
    assert value >= 0, f"{field} must be non-negative: {value!r}"


def test_reporting_endpoints_aggregate_upstream_services() -> None:
    with client() as api:
        customers = api.get("/api/reporting/customers")
        assert customers.status_code == 200, customers.text
        customer_report = customers.json()
        assert_non_negative_integer(customer_report["customers"], "customers")

        tasks = api.get("/api/reporting/tasks")
        assert tasks.status_code == 200, tasks.text
        task_report = tasks.json()
        assert_non_negative_integer(task_report["open_tasks"], "open_tasks")

        billing = api.get("/api/reporting/billing")
        assert billing.status_code == 200, billing.text
        billing_report = billing.json()
        assert_non_negative_integer(billing_report["pending_invoices"], "pending_invoices")

        summary = api.get("/api/reporting/summary")
        assert summary.status_code == 200, summary.text
        summary_report = summary.json()
        assert set(summary_report) == {"customers", "open_tasks", "pending_invoices"}
        assert_non_negative_integer(summary_report["customers"], "customers")
        assert_non_negative_integer(summary_report["open_tasks"], "open_tasks")
        assert_non_negative_integer(summary_report["pending_invoices"], "pending_invoices")


def test_reporting_api_exposes_its_health_contract() -> None:
    with client() as api:
        response = api.get("/api/reporting/health")

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok"}


def test_routed_openapi_contains_reporting_routes() -> None:
    with client() as api:
        response = api.get("/api/reporting/openapi.json")

    assert response.status_code == 200, response.text
    paths = response.json()["paths"]
    assert "/api/reporting/customers" in paths
    assert "/api/reporting/tasks" in paths
    assert "/api/reporting/billing" in paths
    assert "/api/reporting/summary" in paths
