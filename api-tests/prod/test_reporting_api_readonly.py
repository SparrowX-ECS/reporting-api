import os

import httpx


BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")


def client() -> httpx.Client:
    if not BASE_URL:
        raise RuntimeError("BASE_URL must point to the deployed reporting-api service")
    return httpx.Client(base_url=BASE_URL, timeout=20.0, follow_redirects=True)


def test_health_endpoint() -> None:
    with client() as api:
        response = api.get("/api/reporting/health")

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok"}


def test_report_endpoints_are_readable() -> None:
    paths = (
        "/api/reporting/customers",
        "/api/reporting/tasks",
        "/api/reporting/billing",
        "/api/reporting/summary",
    )

    with client() as api:
        for path in paths:
            response = api.get(path)
            assert response.status_code == 200, f"{path}: {response.text}"
            assert isinstance(response.json(), dict)


def test_openapi_contains_reporting_routes() -> None:
    with client() as api:
        response = api.get("/openapi.json")

    assert response.status_code == 200, response.text
    paths = response.json()["paths"]
    assert "/api/reporting/customers" in paths
    assert "/api/reporting/tasks" in paths
    assert "/api/reporting/billing" in paths
    assert "/api/reporting/summary" in paths


def test_metrics_endpoint_is_readable() -> None:
    with client() as api:
        response = api.get("/metrics")

    assert response.status_code == 200, response.text
    assert "text/plain" in response.headers.get("content-type", "")
