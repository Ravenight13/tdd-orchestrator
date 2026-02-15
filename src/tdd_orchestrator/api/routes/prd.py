"""PRD submission and status endpoints.

Endpoints:
- POST /prd/submit - Submit a PRD for processing
- GET /prd/status/{run_id} - Check status of a PRD run
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tdd_orchestrator.api.dependencies import get_db_dep

router = APIRouter()

# In-memory tracking for active PRD runs
_active_runs: dict[str, dict[str, Any]] = {}
_rate_counter: list[float] = []
MAX_CONTENT_SIZE = 1_048_576  # 1MB
MAX_RUNS_PER_HOUR = 5


class PrdSubmitRequest(BaseModel):
    """Request body for PRD submission."""

    name: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    workers: int = Field(default=2, ge=1, le=8)
    dry_run: bool = False
    create_pr: bool = False


class PrdSubmitResponse(BaseModel):
    """Response for PRD submission."""

    run_id: str
    status: str
    message: str


class PrdStatusResponse(BaseModel):
    """Response for PRD status check."""

    run_id: str
    stage: str
    status: str
    task_count: int | None = None
    error_message: str | None = None


def _sanitize_name(name: str) -> str:
    """Sanitize a name for use in branch names."""
    sanitized = "".join(c if c.isalnum() or c in "-_" else "-" for c in name.lower())
    return sanitized[:50].strip("-")


def _check_rate_limit() -> bool:
    """Check if rate limit allows a new submission."""
    now = time.time()
    cutoff = now - 3600
    _rate_counter[:] = [t for t in _rate_counter if t > cutoff]
    return len(_rate_counter) < MAX_RUNS_PER_HOUR


def _has_active_run() -> bool:
    """Check if there's an active PRD run."""
    return any(
        r["status"] in ("pending", "running")
        for r in _active_runs.values()
    )


async def _run_prd_pipeline(
    run_id: str,
    name: str,
    content: str,
    workers: int,
    dry_run: bool,
    create_pr: bool,
) -> None:
    """Simulate PRD pipeline execution.

    In production this would call the actual decomposition and execution
    pipeline. For MVP, this simulates the stages with delays.
    """
    # Suppress unused arguments for now (will be wired in production)
    _ = name, content, workers, dry_run, create_pr

    stages = ["init", "branch", "decompose", "execute", "pr", "done"]
    try:
        for stage in stages:
            if run_id not in _active_runs:
                return
            _active_runs[run_id]["stage"] = stage
            _active_runs[run_id]["status"] = "running"
            # Simulate work
            await asyncio.sleep(0.1)

        _active_runs[run_id]["status"] = "completed"
        _active_runs[run_id]["stage"] = "done"
    except Exception as e:
        if run_id in _active_runs:
            _active_runs[run_id]["status"] = "failed"
            _active_runs[run_id]["error_message"] = str(e)


@router.post("/submit", response_model=PrdSubmitResponse)
async def submit_prd(
    request: PrdSubmitRequest,
    db: Any = Depends(get_db_dep),
) -> dict[str, Any]:
    """Submit a PRD for processing.

    Validates input, checks rate limits, and spawns pipeline as asyncio task.

    Args:
        request: The PRD submission request.
        db: Database dependency (injected).

    Returns:
        PrdSubmitResponse with run_id and status.

    Raises:
        HTTPException: 400 for validation errors, 409 for concurrent runs,
            429 for rate limit.
    """
    # Suppress unused db for now (will be wired in production)
    _ = db

    # Content size check
    if len(request.content.encode("utf-8")) > MAX_CONTENT_SIZE:
        raise HTTPException(
            status_code=400, detail="PRD content exceeds 1MB limit"
        )

    # Sanitize name
    sanitized_name = _sanitize_name(request.name)
    if not sanitized_name:
        raise HTTPException(
            status_code=400, detail="Invalid name after sanitization"
        )

    # Concurrent run check
    if _has_active_run():
        raise HTTPException(
            status_code=409, detail="A PRD pipeline is already running"
        )

    # Rate limit check
    if not _check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded (max 5 per hour)"
        )

    run_id = str(uuid.uuid4())
    _rate_counter.append(time.time())
    _active_runs[run_id] = {
        "run_id": run_id,
        "stage": "pending",
        "status": "pending",
        "task_count": None,
        "error_message": None,
        "name": sanitized_name,
    }

    # Spawn pipeline as background task
    asyncio.create_task(
        _run_prd_pipeline(
            run_id=run_id,
            name=sanitized_name,
            content=request.content,
            workers=request.workers,
            dry_run=request.dry_run,
            create_pr=request.create_pr,
        )
    )

    return {
        "run_id": run_id,
        "status": "pending",
        "message": f"PRD '{sanitized_name}' submitted for processing",
    }


@router.get("/status/{run_id}", response_model=PrdStatusResponse)
async def get_prd_status(run_id: str) -> dict[str, Any]:
    """Get status of a PRD run.

    Args:
        run_id: The run ID to check.

    Returns:
        PrdStatusResponse with current stage and status.

    Raises:
        HTTPException: 404 if run not found.
    """
    run = _active_runs.get(run_id)
    if run is None:
        raise HTTPException(
            status_code=404, detail=f"PRD run {run_id} not found"
        )

    return {
        "run_id": run["run_id"],
        "stage": run["stage"],
        "status": run["status"],
        "task_count": run.get("task_count"),
        "error_message": run.get("error_message"),
    }
