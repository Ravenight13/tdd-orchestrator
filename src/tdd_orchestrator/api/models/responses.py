"""API response models for TDD Orchestrator.

These Pydantic models handle serialization of database ORM objects to API responses,
with automatic JSON deserialization for JSON-encoded database columns.
"""

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    computed_field,
    field_validator,
)


class TaskResponse(BaseModel):
    """Response model for Task entities.

    Handles JSON-encoded columns (subtasks, config) with automatic deserialization.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    spec: str
    status: str
    created_at: datetime
    subtasks: list[Any] | None
    config: dict[str, Any]

    @field_validator("subtasks", mode="before")
    @classmethod
    def deserialize_subtasks(cls, v: Any) -> list[Any] | None:
        """Deserialize subtasks from JSON string to list."""
        if isinstance(v, str):
            try:
                result = json.loads(v)
                # Handle "null" JSON string
                if result is None:
                    return None
                if not isinstance(result, list):
                    raise ValueError(
                        f"Expected list in subtasks field, got {type(result).__name__}"
                    )
                return result
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in subtasks field: {e}") from e
        return v  # type: ignore[no-any-return]

    @field_validator("config", mode="before")
    @classmethod
    def deserialize_config(cls, v: Any) -> dict[str, Any]:
        """Deserialize config from JSON string to dict."""
        if isinstance(v, str):
            try:
                result = json.loads(v)
                # Handle "null" JSON string - convert to empty dict
                if result is None:
                    return {}
                if not isinstance(result, dict):
                    raise ValueError(
                        f"Expected dict in config field, got {type(result).__name__}"
                    )
                return result
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in config field: {e}") from e
        return v  # type: ignore[no-any-return]


class AttemptResponse(BaseModel):
    """Response model for Attempt entities.

    Handles JSON-encoded columns (test_output, error_info) with automatic deserialization.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    attempt_number: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    test_output: dict[str, Any] | None
    error_info: dict[str, Any] | None

    @field_validator("test_output", mode="before")
    @classmethod
    def deserialize_test_output(cls, v: Any) -> dict[str, Any] | None:
        """Deserialize test_output from JSON string to dict."""
        if isinstance(v, str):
            try:
                result = json.loads(v)
                # Handle "null" JSON string
                if result is None:
                    return None
                if not isinstance(result, dict):
                    raise ValueError(
                        f"Expected dict in test_output field, got {type(result).__name__}"
                    )
                return result
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in test_output field: {e}") from e
        return v  # type: ignore[no-any-return]

    @field_validator("error_info", mode="before")
    @classmethod
    def deserialize_error_info(cls, v: Any) -> dict[str, Any] | None:
        """Deserialize error_info from JSON string to dict."""
        if v is None:
            return None
        if isinstance(v, str):
            try:
                result = json.loads(v)
                if result is None:
                    return None
                if not isinstance(result, dict):
                    raise ValueError(
                        f"Expected dict in error_info field, got {type(result).__name__}"
                    )
                return result
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in error_info field: {e}") from e
        return v  # type: ignore[no-any-return]


class ErrorResponse(BaseModel):
    """Response model for API errors.

    Standard error response structure with optional details field.
    """

    error_code: str
    message: str
    details: dict[str, Any] | None = None


class SSEEventData(BaseModel):
    """Response model for Server-Sent Events (SSE).

    Structure for SSE event data with event type and payload.
    """

    event: str
    data: dict[str, Any]


class WorkerResponse(BaseModel):
    """Response model for Worker entities."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    current_task_id: str | None
    started_at: datetime


class CircuitBreakerResponse(BaseModel):
    """Response model for Circuit Breaker entities.

    Fields match the v_circuit_breaker_status DB view.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    level: str
    identifier: str
    state: str
    failure_count: int
    success_count: int = 0
    extensions_count: int = 0
    opened_at: str | None = None
    last_failure_at: str | None = None
    last_success_at: str | None = None
    last_state_change_at: str | None = None
    version: int = 1
    run_id: int | None = None


class CircuitHealthSummary(BaseModel):
    """Response model for per-level circuit health (v_circuit_health_summary view)."""

    model_config = ConfigDict(from_attributes=True)

    level: str
    total_circuits: int
    closed_count: int
    open_count: int
    half_open_count: int


class TaskDetailResponse(BaseModel):
    """Response model that wraps a TaskResponse with metadata.

    Used for single task detail endpoints.
    """

    task: TaskResponse
    metadata: dict[str, Any]


class TaskListResponse(BaseModel):
    """Response model that wraps a list of TaskResponse with pagination.

    Used for task list endpoints with pagination support.
    """

    tasks: list[TaskResponse]
    total: int
    limit: int
    offset: int


class WorkerListResponse(BaseModel):
    """Response model that wraps a list of WorkerResponse with pagination.

    Used for worker list endpoints with pagination support.
    """

    workers: list[WorkerResponse]
    total: int
    limit: int
    offset: int


class CircuitBreakerListResponse(BaseModel):
    """Response model that wraps a list of CircuitBreakerResponse with pagination.

    Used for circuit breaker list endpoints with pagination support.
    """

    circuits: list[CircuitBreakerResponse]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""

    status: Literal["ok", "degraded"]
    version: str
    uptime_seconds: float

    @field_validator("status")
    @classmethod
    def validate_status_not_empty(cls, v: str) -> str:
        """Ensure status is not empty."""
        if not v:
            raise ValueError("status cannot be empty")
        return v


class RunResponse(BaseModel):
    """Response model for individual run information."""

    run_id: str
    status: Literal["pending", "running", "completed", "failed"]
    created_at: str
    task_count: int
    progress: float | None = None


class ProgressResponse(BaseModel):
    """Response model for progress tracking."""

    total_tasks: int = Field(ge=0)
    completed_tasks: int = Field(ge=0)
    failed_tasks: int = Field(ge=0)
    pending_tasks: int = Field(ge=0)

    @field_validator("total_tasks", "completed_tasks", "failed_tasks", "pending_tasks")
    @classmethod
    def validate_non_negative(cls, v: int) -> int:
        """Ensure task counts are non-negative."""
        if v < 0:
            raise ValueError("task count cannot be negative")
        return v

    @field_validator("pending_tasks")
    @classmethod
    def validate_task_sum(cls, v: int, info: ValidationInfo) -> int:
        """Ensure completed + failed + pending equals total."""
        if info.data:
            total = info.data.get("total_tasks", 0)
            completed = info.data.get("completed_tasks", 0)
            failed = info.data.get("failed_tasks", 0)
            if completed + failed + v != total:
                raise ValueError("completed + failed + pending must equal total_tasks")
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def completion_percentage(self) -> float:
        """Calculate completion percentage."""
        if self.total_tasks == 0:
            return 0.0
        return (self.completed_tasks / self.total_tasks) * 100.0


class RunListResponse(BaseModel):
    """Response model for list of runs."""

    runs: list[RunResponse]


class StatsResponse(BaseModel):
    """Response model for statistics endpoint."""

    pass
