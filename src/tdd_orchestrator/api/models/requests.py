"""API request and query parameter models with Pydantic validation."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TaskFilterParams(BaseModel):
    """Query parameters for filtering tasks."""

    model_config = {"extra": "forbid"}

    status: Literal["pending", "running", "completed", "failed"] | None = None
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class TaskRetryRequest(BaseModel):
    """Request model for retrying a task."""

    model_config = {"extra": "forbid"}

    task_id: str
    max_retries: int = 3

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        """Validate task_id is not empty or whitespace."""
        if not v or not v.strip():
            raise ValueError("task_id must not be empty or whitespace")
        return v

    @field_validator("max_retries")
    @classmethod
    def validate_max_retries(cls, v: int) -> int:
        """Validate max_retries is positive."""
        if v < 1:
            raise ValueError("max_retries must be at least 1")
        return v


class CircuitResetRequest(BaseModel):
    """Request model for resetting a circuit breaker."""

    model_config = {"extra": "forbid"}

    service_name: str
    reason: str | None = None

    @field_validator("service_name")
    @classmethod
    def validate_service_name(cls, v: str) -> str:
        """Validate service_name is not empty or whitespace."""
        if not v or not v.strip():
            raise ValueError("service_name must not be empty or whitespace")
        return v
