import os

from pydantic import BaseModel, Field


class Settings(BaseModel):
    customer_api_url: str = Field(default="http://localhost:8001")
    task_api_url: str = Field(default="http://localhost:8002")
    billing_api_url: str = Field(default="http://localhost:8003")
    upstream_timeout_seconds: float = Field(default=5.0, gt=0, le=60)

    @classmethod
    def from_environment(cls) -> "Settings":
        values = {
            "customer_api_url": os.getenv("CUSTOMER_API_URL", "http://localhost:8001").rstrip("/"),
            "task_api_url": os.getenv("TASK_API_URL", "http://localhost:8002").rstrip("/"),
            "billing_api_url": os.getenv("BILLING_API_URL", "http://localhost:8003").rstrip("/"),
        }
        timeout = os.getenv("UPSTREAM_TIMEOUT_SECONDS")
        if timeout is not None:
            values["upstream_timeout_seconds"] = timeout
        return cls.model_validate(values)
