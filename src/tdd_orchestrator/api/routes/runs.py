"""Runs router for listing runs and retrieving run details."""

from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from tdd_orchestrator.api.dependencies import get_db_dep

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


def _run_row_to_dict(row: Any) -> dict[str, Any]:
    """Convert an execution_runs DB row to an API response dict."""
    return {
        "id": str(row["id"]),
        "task_id": None,
        "status": str(row["status"]),
        "started_at": str(row["started_at"]),
        "worker_id": None,
    }


@router.get("")
async def get_runs(
    status: RunStatus | None = Query(None, description="Filter by run status"),
    db: Any = Depends(get_db_dep),
) -> dict[str, Any]:
    """Get list of runs with optional status filter.

    Args:
        status: Optional status filter (pending, running, completed, failed).

    Returns:
        RunListResponse with runs list and total count.
    """
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        query = "SELECT * FROM execution_runs WHERE 1=1"
        params: list[Any] = []
        if status is not None:
            query += " AND status = ?"
            params.append(status.value)
        query += " ORDER BY started_at DESC"
        async with db._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        runs = [_run_row_to_dict(row) for row in rows]
        return {"runs": runs, "total": len(runs)}
    status_str = status.value if status else None
    return list_runs(status=status_str)


@router.get("/current", response_model=None)
async def get_current_run_endpoint(
    db: Any = Depends(get_db_dep),
) -> dict[str, Any] | JSONResponse:
    """Get the current active run.

    Returns:
        RunResponse for the active run, or JSONResponse with 404 error.
    """
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        async with db._conn.execute(
            "SELECT * FROM execution_runs WHERE status = 'running' LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
        if row is not None:
            return _run_row_to_dict(row)
        return JSONResponse(
            status_code=404,
            content={"detail": "No active run", "error_code": "ERR-RUN-404"},
        )
    run = get_current_run()
    if run is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "No active run", "error_code": "ERR-RUN-404"},
        )
    return run


@router.get("/{run_id}", response_model=None)
async def get_run_by_id_endpoint(
    run_id: str, db: Any = Depends(get_db_dep)
) -> dict[str, Any] | JSONResponse:
    """Get a specific run by ID.

    Args:
        run_id: The unique run identifier.

    Returns:
        RunResponse with full run details, or JSONResponse with 404 error.
    """
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        try:
            run_id_int = int(run_id)
        except ValueError:
            return JSONResponse(
                status_code=404,
                content={"detail": "Run not found", "error_code": "ERR-RUN-404"},
            )
        async with db._conn.execute(
            "SELECT * FROM execution_runs WHERE id = ?", (run_id_int,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is not None:
            return _run_row_to_dict(row)
        return JSONResponse(
            status_code=404,
            content={"detail": "Run not found", "error_code": "ERR-RUN-404"},
        )
    run = get_run_by_id(run_id)
    if run is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "Run not found", "error_code": "ERR-RUN-404"},
        )
    return run
