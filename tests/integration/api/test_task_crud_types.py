"""Type alias classes for task CRUD API response structures.

These classes represent the expected API response structures
and are exported for documentation and typing purposes.
"""

from __future__ import annotations


class TaskResponse:
    """Represents a task in list responses."""

    pass


class TaskDetailResponse:
    """Represents a detailed task response."""

    pass


class TaskListResponse:
    """Represents a paginated list of tasks."""

    pass


class TaskFilterParams:
    """Represents query parameters for filtering tasks."""

    pass


class TaskRetryRequest:
    """Represents a request to retry a failed task."""

    pass


__all__ = [
    "TaskResponse",
    "TaskDetailResponse",
    "TaskListResponse",
    "TaskFilterParams",
    "TaskRetryRequest",
]
