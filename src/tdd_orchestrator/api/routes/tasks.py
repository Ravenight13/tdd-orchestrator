"""Tasks router for listing tasks with filtering and pagination."""

from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from tdd_orchestrator.api.dependencies import get_broadcaster_dep, get_db_dep

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


def get_task_stats() -> dict[str, int]:
    """Get aggregate task counts by status.

    This is a placeholder function that will be replaced with actual
    database queries. For now, it returns all zeros.

    Returns:
        A dictionary with counts for each status and total count.
    """
    return {
        "pending": 0,
        "running": 0,
        "passed": 0,
        "failed": 0,
        "total": 0,
    }


def get_task_progress() -> dict[str, float]:
    """Get phase-level completion percentages.

    This is a placeholder function that will be replaced with actual
    database queries. For now, it returns an empty dictionary.

    Returns:
        A dictionary mapping phase names to completion percentages.
    """
    return {}


def get_task_detail(task_key: str) -> dict[str, Any] | None:
    """Get task detail with full attempt history.

    This is a placeholder function that will be replaced with actual
    database queries. For now, it returns None.

    Args:
        task_key: The unique task identifier.

    Returns:
        A dictionary with task details and nested attempts, or None if not found.
    """
    return None


def retry_task(task_key: str) -> dict[str, Any]:
    """Reset a task's status to pending.

    This is a placeholder function that will be replaced with actual
    database queries. For now, it returns a basic response structure.

    Args:
        task_key: The unique task identifier.

    Returns:
        A dictionary with the updated task data showing status as pending.
    """
    return {
        "task_key": task_key,
        "status": "pending",
    }


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
            # Map API status values to DB status values
            db_status_map: dict[str, list[str]] = {
                "pending": ["pending"],
                "running": ["in_progress"],
                "completed": ["passing", "complete"],
                "failed": ["blocked", "blocked-static-review"],
            }
            db_statuses = db_status_map.get(status.value, [status.value])
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
            db_statuses_c = db_status_map.get(status.value, [status.value])
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
        # Map DB status to API status for consistency with metrics endpoint
        api_status_map: dict[str, str] = {
            "pending": "pending",
            "in_progress": "running",
            "passing": "passed",
            "complete": "passed",
            "blocked": "failed",
            "blocked-static-review": "failed",
        }
        tasks_list = [
            {
                "id": str(row["task_key"]),
                "title": str(row["title"]),
                "status": api_status_map.get(str(row["status"]), str(row["status"])),
                "phase": int(row["phase"]),
                "sequence": int(row["sequence"]),
                "complexity": str(row["complexity"]) if row["complexity"] else "medium",
            }
            for row in rows
        ]
        return {"tasks": tasks_list, "total": total, "limit": limit, "offset": offset}
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


@router.get("/stats")
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
    return get_task_stats()


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
        return progress
    return get_task_progress()


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
    api_status_map: dict[str, str] = {
        "pending": "pending",
        "in_progress": "running",
        "passing": "passed",
        "complete": "passed",
        "blocked": "failed",
        "blocked-static-review": "failed",
    }
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        task: dict[str, Any] | None = await db.get_task_by_key(task_key)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        task_id = int(task["id"])
        attempts: list[dict[str, Any]] = await db.get_stage_attempts(task_id)

        return {
            "id": str(task["task_key"]),
            "title": str(task["title"]),
            "status": api_status_map.get(str(task["status"]), str(task["status"])),
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
    task_detail = get_task_detail(task_key)
    if task_detail is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task_detail


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
    api_status_map: dict[str, str] = {
        "pending": "pending",
        "in_progress": "running",
        "passing": "passed",
        "complete": "passed",
        "blocked": "failed",
        "blocked-static-review": "failed",
    }
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        task: dict[str, Any] | None = await db.get_task_by_key(task_key)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        api_status = api_status_map.get(str(task["status"]), str(task["status"]))
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
            await broadcaster.publish(
                {
                    "event": "task_status_changed",
                    "task_key": task_key,
                    "status": "pending",
                }
            )
        except Exception:
            pass

        return {"task_key": task_key, "status": "pending"}

    # Fallback to placeholder
    task_detail = get_task_detail(task_key)
    if task_detail is None:
        raise HTTPException(status_code=404, detail="Task not found")

    current_status = task_detail.get("status")
    if current_status != "failed":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot retry task with status '{current_status}'."
                " Only failed tasks can be retried."
            ),
        )

    updated_task = retry_task(task_key)

    try:
        await broadcaster.publish(
            {
                "event": "task_status_changed",
                "task_key": task_key,
                "status": "pending",
            }
        )
    except Exception:
        pass

    return updated_task
