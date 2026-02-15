"""Tasks router for listing tasks with filtering and pagination."""

import json
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from tdd_orchestrator.api.dependencies import get_broadcaster_dep, get_db_dep
from tdd_orchestrator.api.models.responses import StatsResponse
from tdd_orchestrator.api.sse import SSEEvent

router = APIRouter()

# Maps API status values → DB status values (for filtering incoming requests)
DB_STATUS_MAP: dict[str, list[str]] = {
    "pending": ["pending"],
    "running": ["in_progress"],
    "completed": ["passing", "complete"],
    "failed": ["blocked", "blocked-static-review"],
}

# Maps DB status values → API status values (for outgoing responses)
API_STATUS_MAP: dict[str, str] = {
    "pending": "pending",
    "in_progress": "running",
    "passing": "passed",
    "complete": "passed",
    "blocked": "failed",
    "blocked-static-review": "failed",
}


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


@router.get("")
async def get_tasks(
    status: TaskStatus | None = Query(None, description="Filter by task status"),
    phase: TaskPhase | None = Query(None, description="Filter by task phase"),
    complexity: TaskComplexity | None = Query(
        None, description="Filter by task complexity"
    ),
    limit: int = Query(20, ge=0, description="Maximum number of tasks to return"),
    offset: int = Query(0, ge=0, description="Number of tasks to skip"),
    db: Any = Depends(get_db_dep),
) -> dict[str, Any]:
    """Get list of tasks with optional filtering and pagination.

    Args:
        status: Optional status filter (pending, running, completed, failed).
        phase: Optional phase filter (decomposition, red, green, verify, refactor).
        complexity: Optional complexity filter (low, medium, high).
        limit: Maximum number of tasks to return (default 20).
        offset: Number of tasks to skip for pagination (default 0).
        db: Database dependency (injected).

    Returns:
        TaskListResponse with tasks list, total count, limit, and offset.
    """
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        query = "SELECT * FROM tasks WHERE 1=1"
        params: list[Any] = []
        if status is not None:
            db_statuses = DB_STATUS_MAP.get(status.value, [status.value])
            placeholders = ",".join("?" for _ in db_statuses)
            query += f" AND status IN ({placeholders})"
            params.extend(db_statuses)
        if phase is not None:
            query += " AND phase = ?"
            params.append(phase.value)
        if complexity is not None:
            query += " AND complexity = ?"
            params.append(complexity.value)
        query += " ORDER BY phase, sequence"
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        async with db._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        # Get total count without limit/offset
        count_query = "SELECT COUNT(*) as cnt FROM tasks WHERE 1=1"
        count_params: list[Any] = []
        if status is not None:
            db_statuses_c = DB_STATUS_MAP.get(status.value, [status.value])
            placeholders_c = ",".join("?" for _ in db_statuses_c)
            count_query += f" AND status IN ({placeholders_c})"
            count_params.extend(db_statuses_c)
        if phase is not None:
            count_query += " AND phase = ?"
            count_params.append(phase.value)
        if complexity is not None:
            count_query += " AND complexity = ?"
            count_params.append(complexity.value)
        async with db._conn.execute(count_query, count_params) as cursor:
            count_row = await cursor.fetchone()
        total = int(count_row["cnt"]) if count_row else 0
        tasks_list = [
            {
                "id": str(row["task_key"]),
                "title": str(row["title"]),
                "status": API_STATUS_MAP.get(str(row["status"]), str(row["status"])),
                "phase": int(row["phase"]),
                "sequence": int(row["sequence"]),
                "complexity": str(row["complexity"]) if row["complexity"] else "medium",
            }
            for row in rows
        ]
        return {"tasks": tasks_list, "total": total, "limit": limit, "offset": offset}
    raise HTTPException(status_code=503, detail="Database not available")


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: Any = Depends(get_db_dep)) -> dict[str, int]:
    """Get aggregate task counts by status.

    Args:
        db: Database dependency (injected).

    Returns:
        Dictionary with counts for each status (pending, running, passed, failed)
        and total count of all tasks.
    """
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        counts: dict[str, int] = {"pending": 0, "running": 0, "passed": 0, "failed": 0}
        async with db._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status"
        ) as cursor:
            async for row in cursor:
                db_status = str(row["status"])
                count = int(row["cnt"])
                if db_status == "pending":
                    counts["pending"] += count
                elif db_status == "in_progress":
                    counts["running"] += count
                elif db_status in ("passing", "complete"):
                    counts["passed"] += count
                elif db_status in ("blocked", "blocked-static-review"):
                    counts["failed"] += count
        total = sum(counts.values())
        return {
            "pending": counts["pending"],
            "running": counts["running"],
            "passed": counts["passed"],
            "failed": counts["failed"],
            "total": total,
        }
    raise HTTPException(status_code=503, detail="Database not available")


@router.get("/progress")
async def get_progress(db: Any = Depends(get_db_dep)) -> dict[str, Any]:
    """Get task completion progress.

    Args:
        db: Database dependency (injected).

    Returns:
        Dictionary with total, completed, percentage, and by_status breakdown.
    """
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        progress: dict[str, Any] = await db.get_progress()
        # Map DB status keys to API vocabulary for consistency
        raw_by_status = progress.get("by_status", {})
        mapped_by_status: dict[str, int] = {
            "pending": int(raw_by_status.get("pending", 0)),
            "running": int(raw_by_status.get("in_progress", 0)),
            "passed": int(raw_by_status.get("passing", 0))
            + int(raw_by_status.get("complete", 0)),
            "failed": int(raw_by_status.get("blocked", 0))
            + int(raw_by_status.get("blocked-static-review", 0)),
        }
        progress["by_status"] = mapped_by_status
        return progress
    raise HTTPException(status_code=503, detail="Database not available")


@router.get("/{task_key}")
async def get_task_detail_endpoint(
    task_key: str, db: Any = Depends(get_db_dep)
) -> dict[str, Any]:
    """Get task detail with full attempt history.

    Args:
        task_key: The unique task identifier.
        db: Database dependency (injected).

    Returns:
        TaskDetailResponse with task details and nested AttemptResponse objects.

    Raises:
        HTTPException: 404 if task not found.
    """
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        task: dict[str, Any] | None = await db.get_task_by_key(task_key)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        task_id = int(task["id"])
        attempts: list[dict[str, Any]] = await db.get_stage_attempts(task_id)

        return {
            "id": str(task["task_key"]),
            "title": str(task["title"]),
            "status": API_STATUS_MAP.get(str(task["status"]), str(task["status"])),
            "phase": int(task["phase"]),
            "sequence": int(task["sequence"]),
            "complexity": str(task["complexity"]) if task.get("complexity") else "medium",
            "attempts": [
                {
                    "id": int(a["id"]),
                    "stage": str(a["stage"]),
                    "attempt_number": int(a["attempt_number"]),
                    "success": bool(a["success"]),
                    "error_message": (
                        str(a["error_message"]) if a.get("error_message") else None
                    ),
                    "started_at": str(a["started_at"]) if a.get("started_at") else None,
                }
                for a in attempts
            ],
        }
    raise HTTPException(status_code=503, detail="Database not available")


@router.post("/{task_key}/retry")
async def retry_task_endpoint(
    task_key: str,
    db: Any = Depends(get_db_dep),
    broadcaster: Any = Depends(get_broadcaster_dep),
) -> dict[str, Any]:
    """Retry a failed task by resetting its status to pending.

    Args:
        task_key: The unique task identifier.
        db: Database dependency (injected).
        broadcaster: The SSEBroadcaster instance (injected dependency).

    Returns:
        TaskResponse with task_key and updated status='pending'.

    Raises:
        HTTPException: 404 if task not found.
        HTTPException: 409 if task status is not retryable (only 'failed' can be retried).
    """
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        task: dict[str, Any] | None = await db.get_task_by_key(task_key)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        api_status = API_STATUS_MAP.get(str(task["status"]), str(task["status"]))
        if api_status != "failed":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot retry task with status '{api_status}'."
                    " Only failed tasks can be retried."
                ),
            )

        await db.update_task_status(task_key, "pending")

        try:
            sse_event = SSEEvent(
                event="task_status_changed",
                data=json.dumps({"task_key": task_key, "status": "pending"}),
            )
            await broadcaster.publish(sse_event)
        except Exception:
            pass

        return {"task_key": task_key, "status": "pending"}

    raise HTTPException(status_code=503, detail="Database not available")
