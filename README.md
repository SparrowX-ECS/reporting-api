# Reporting API

Read-only aggregation service for the fictional SparrowX SaaS platform. This stateless demonstration workload shows internal backend-to-backend traffic: it calls `customer-api`, `task-api`, and `billing-api` through ECS Service Connect and combines their responses into reports.

## Service responsibilities

- Aggregate customer, task, and billing information.
- Demonstrate private service-to-service communication.
- Expose health, smoke-test, and Prometheus-compatible metrics endpoints.
- Run without a database of its own.

## API documentation

FastAPI documentation is available at `/docs` (Swagger UI), `/redoc` (ReDoc), and `/openapi.json` (OpenAPI schema). The main API prefix is `/api/reporting`:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/reporting/customers` | Customer summary |
| `GET` | `/api/reporting/tasks` | Open-task summary |
| `GET` | `/api/reporting/billing` | Pending-invoice summary |
| `GET` | `/api/reporting/summary` | Combined report |
| `GET` | `/health` | Container/target-group health check |
| `GET` | `/api/reporting/health` | API smoke-test health check |
| `GET` | `/metrics` | Prometheus metrics |

## Runtime environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `CUSTOMER_API_URL` | No | Base URL for Customer API; defaults to `http://localhost:8001`. In ECS, Service Connect supplies `http://customer-api:8000`. |
| `TASK_API_URL` | No | Base URL for Task API; defaults to `http://localhost:8002`. In ECS, Service Connect supplies `http://task-api:8000`. |
| `BILLING_API_URL` | No | Base URL for Billing API; defaults to `http://localhost:8003`. In ECS, Service Connect supplies `http://billing-api:8000`. |
| `UPSTREAM_TIMEOUT_SECONDS` | No | Timeout for upstream calls; defaults to `5` seconds and must be greater than `0` and no more than `60`. |
| `CORS_ALLOW_ORIGINS` | No | Comma-separated browser origins; defaults to local development origins. |

## Local development

```bash
python -m pip install -r requirements-dev.txt
pytest
uvicorn src.main:app --reload --port 8000
```

Set the three upstream URLs to locally running services, then open <http://localhost:8000/docs>.

## CI/CD cycle

Pull requests run Python tests without PostgreSQL, build one immutable commit-SHA image, scan it with Trivy, and publish metadata. A merge to `main` resolves the image, deploys it to `dev`, runs the reporting smoke test, and publishes its tag and digest as the production candidate.

The manually confirmed production workflow verifies the candidate digest, copies the same image from `dev` ECR to `prod` ECR, deploys it, smoke-tests it, and publishes production metadata. The service follows **Build Once, Promote Many** and is not rebuilt for production.

## Environments and deployment tracking

`dev` deploys automatically from `main`; `prod` is promoted manually after development validation. Each environment has separate ECS resources, ECR namespace, upstream configuration, parameter file, URL, SSM metadata path, and GitHub deployment history. See [`ecs-parameters-dev.yaml`](ecs-parameters-dev.yaml) and [`ecs-parameters-prod.yaml`](ecs-parameters-prod.yaml).

## Rollback options

### Git revert

Revert the problematic source or deployment configuration commit and merge it. The normal pipeline will validate and deploy the corrective commit.

### Quicker manual image rollback

1. Open **Deployments**, select the `prod` environment, and open the desired previous deployment.
2. Copy the deployed image tag.
3. Open **Actions → Manual Rollback Production To Selected Image Tag → Run workflow**.
4. Enter `ROLLBACK`, paste the image tag, and run the workflow.

The selected immutable image is redeployed and smoke-tested without rebuilding. ECS deployment circuit-breaker rollback is also enabled.

## Repository variables

| Variable | Description |
| --- | --- |
| `AWS_ACCOUNT_ID` | AWS account containing the ECS platform and ECR repositories. |
| `AWS_REGION` | AWS region used by the workflows. |
| `AWS_ROLE_NAME` | IAM role assumed through GitHub OIDC. |
| `DEV_BASE_URL` | Development smoke-test origin with protocol and domain only. |
| `DEV_DEPLOYED_PARAM_STORE_PATH` | SSM path for the last successful `dev` image. |
| `PROD_BASE_URL` | Production smoke-test origin with protocol and domain only. |
| `PROD_CANDIDATE_PARAM_STORE_PATH` | SSM path for the production candidate image. |
| `PROD_DEPLOYED_PARAM_STORE_PATH` | SSM path for the last successful `prod` image. |

The smoke-test workflow appends `/api/reporting/health` from the selected parameter file to the base URL.

## Container and deployment configuration

- Container port: `8000`.
- ALB path: `/api/reporting/*`.
- Health check: `/health`.
- Smoke-test path: `/api/reporting/health`.
- Database: disabled; upstream services are reached through Service Connect.

## License

This is a proprietary portfolio project. It is publicly viewable but not open source. All rights are reserved. See [LICENSE.md](LICENSE.md).
