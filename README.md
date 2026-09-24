# SparrowX Labs Reporting API

The read-only Reporting API is owned by Noah Taylor (Analytics Team). It aggregates operational statistics from the Customer, Task, and Billing APIs over internal ECS Service Connect HTTP and has no database of its own.

## API contract

| Method | Path | Response |
| --- | --- | --- |
| `GET` | `/api/reporting/customers` | `{ "customers": 1240 }` |
| `GET` | `/api/reporting/tasks` | `{ "open_tasks": 87 }` |
| `GET` | `/api/reporting/billing` | `{ "pending_invoices": 31 }` |
| `GET` | `/api/reporting/summary` | The three fields above combined |

Open tasks are `TODO` and `IN_PROGRESS`; pending invoices are `PENDING`. Upstream timeout errors return `504`; other upstream failures or invalid responses return `502`.

## Local development

From this directory:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
pytest -q
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

The service is independently runnable for `/health`, `/docs`, `/openapi.json`, and `/metrics`. Report calls require the upstream APIs unless their HTTP calls are mocked in tests.

## Configuration and endpoints

The defaults assume Customer API on `http://localhost:8001`, Task API on `http://localhost:8002`, and Billing API on `http://localhost:8003`. Override them with `CUSTOMER_API_URL`, `TASK_API_URL`, and `BILLING_API_URL`. `UPSTREAM_TIMEOUT_SECONDS` defaults to `5`.

```bash
CUSTOMER_API_URL=http://customer-api:8000 \
TASK_API_URL=http://task-api:8000 \
BILLING_API_URL=http://billing-api:8000 \
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

- OpenAPI UI: <http://localhost:8000/docs>
- OpenAPI JSON: <http://localhost:8000/openapi.json>
- Health: `GET /health` returns `{"status":"ok"}`
- Metrics: <http://localhost:8000/metrics>

The importable Grafana example is `monitoring/grafana-dashboard.json`; it assumes Prometheus uses the `job="reporting-api"` label.

## Docker

```bash
docker build -t reporting-api .
docker run --rm -p 8000:8000 \
  -e CUSTOMER_API_URL=http://customer-api:8000 \
  -e TASK_API_URL=http://task-api:8000 \
  -e BILLING_API_URL=http://billing-api:8000 \
  reporting-api
```

The image runs as a non-root user. In ECS, the service names resolve through Service Connect; the ALB is used only for external ingress.
