from pydantic import BaseModel, Field


class CustomerReport(BaseModel):
    customers: int = Field(ge=0, description="Total number of customers")


class TaskReport(BaseModel):
    open_tasks: int = Field(ge=0, description="Tasks in TODO or IN_PROGRESS state")


class BillingReport(BaseModel):
    pending_invoices: int = Field(ge=0, description="Invoices currently in PENDING state")


class SummaryReport(CustomerReport, TaskReport, BillingReport):
    """Overall operational summary assembled from all three upstream APIs."""
