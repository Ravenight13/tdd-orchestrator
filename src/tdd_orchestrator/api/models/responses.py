"""API response models for TDD Orchestrator.

These Pydantic models handle serialization of database ORM objects to API responses,
with automatic JSON deserialization for JSON-encoded database columns.
"""

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


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
    """Response model for Circuit Breaker entities."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    state: str
    failure_count: int
    last_failure_at: datetime | None


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

    circuit_breakers: list[CircuitBreakerResponse]
    total: int
    limit: int
    offset: int
