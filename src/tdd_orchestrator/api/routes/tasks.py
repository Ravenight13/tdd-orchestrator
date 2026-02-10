"""Tasks router for listing tasks with filtering and pagination."""

from enum import Enum
from typing import Any

from fastapi import APIRouter, Query

router = APIRouter()


class TaskStatus(str, Enum):
    """Valid task status values."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPhase(str, Enum):
    """Valid task phase values."""

    DECOMPOSITION = "decomposition"
    RED = "red"
    GREEN = "green"
    VERIFY = "verify"
    REFACTOR = "refactor"


class TaskComplexity(str, Enum):
    """Valid task complexity values."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def list_tasks(
    status: str | None = None,
    phase: str | None = None,
    complexity: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """List tasks with filtering and pagination.

    This is a placeholder function that will be replaced with actual
    database queries. For now, it returns an empty result structure.

    Args:
        status: Optional status filter.
        phase: Optional phase filter.
        complexity: Optional complexity filter.
        limit: Maximum number of tasks to return.
        offset: Number of tasks to skip.

    Returns:
        A dictionary with tasks list, total count, limit, and offset.
    """
    return {
        "tasks": [],
        "total": 0,
        "limit": limit,
        "offset": offset,
    }


@router.get("")
def get_tasks(
    status: TaskStatus | None = Query(None, description="Filter by task status"),
    phase: TaskPhase | None = Query(None, description="Filter by task phase"),
    complexity: TaskComplexity | None = Query(
        None, description="Filter by task complexity"
    ),
    limit: int = Query(20, ge=0, description="Maximum number of tasks to return"),
    offset: int = Query(0, ge=0, description="Number of tasks to skip"),
) -> dict[str, Any]:
    """Get list of tasks with optional filtering and pagination.

    Args:
        status: Optional status filter (pending, running, completed, failed).
        phase: Optional phase filter (decomposition, red, green, verify, refactor).
        complexity: Optional complexity filter (low, medium, high).
        limit: Maximum number of tasks to return (default 20).
        offset: Number of tasks to skip for pagination (default 0).

    Returns:
        TaskListResponse with tasks list, total count, limit, and offset.
    """
    # Convert enums to strings for the list_tasks function
    status_str = status.value if status else None
    phase_str = phase.value if phase else None
    complexity_str = complexity.value if complexity else None

    return list_tasks(
        status=status_str,
        phase=phase_str,
        complexity=complexity_str,
        limit=limit,
        offset=offset,
    )
