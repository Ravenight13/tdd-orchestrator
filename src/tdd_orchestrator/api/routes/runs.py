"""Runs router for listing runs and retrieving run details."""

from enum import Enum
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

router = APIRouter()


class RunStatus(str, Enum):
    """Valid run status values."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def list_runs(status: str | None = None) -> dict[str, Any]:
    """List runs with optional status filter.

    This is a placeholder function that will be replaced with actual
    database queries. For now, it returns an empty result structure.

    Args:
        status: Optional status filter.

    Returns:
        A dictionary with runs list and total count.
    """
    return {
        "runs": [],
        "total": 0,
    }


def get_run_by_id(run_id: str) -> dict[str, Any] | None:
    """Get a specific run by ID.

    This is a placeholder function that will be replaced with actual
    database queries. For now, it returns None.

    Args:
        run_id: The unique run identifier.

    Returns:
        A dictionary with run details, or None if not found.
    """
    return None


def get_current_run() -> dict[str, Any] | None:
    """Get the current active run.

    This is a placeholder function that will be replaced with actual
    database queries. For now, it returns None.

    Returns:
        A dictionary with the active run details, or None if no active run exists.
    """
    return None


@router.get("")
def get_runs(
    status: RunStatus | None = Query(None, description="Filter by run status"),
) -> dict[str, Any]:
    """Get list of runs with optional status filter.

    Args:
        status: Optional status filter (pending, running, completed, failed).

    Returns:
        RunListResponse with runs list and total count.
    """
    # Convert enum to string for the list_runs function
    status_str = status.value if status else None

    return list_runs(status=status_str)


@router.get("/current", response_model=None)
def get_current_run_endpoint() -> dict[str, Any] | JSONResponse:
    """Get the current active run.

    Returns:
        RunResponse for the active run, or JSONResponse with 404 error.
    """
    run = get_current_run()
    if run is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "No active run", "error_code": "ERR-RUN-404"},
        )
    return run


@router.get("/{run_id}", response_model=None)
def get_run_by_id_endpoint(run_id: str) -> dict[str, Any] | JSONResponse:
    """Get a specific run by ID.

    Args:
        run_id: The unique run identifier.

    Returns:
        RunResponse with full run details including task summary, or JSONResponse with 404 error.
    """
    run = get_run_by_id(run_id)
    if run is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "Run not found", "error_code": "ERR-RUN-404"},
        )
    return run
