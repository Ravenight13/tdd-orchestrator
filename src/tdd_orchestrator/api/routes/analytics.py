"""Analytics endpoints for dashboard charts.

Endpoints:
- GET /analytics/attempts-by-stage - Attempt stats grouped by stage
- GET /analytics/task-completion-timeline - Task completions over time
- GET /analytics/invocation-stats - Invocation stats grouped by stage
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from tdd_orchestrator.api.dependencies import get_db_dep
from tdd_orchestrator.api.models.responses_analytics import (
    AttemptsByStageResponse,
    InvocationStatsResponse,
    TaskCompletionTimelineResponse,
)

router = APIRouter()


@router.get("/attempts-by-stage", response_model=AttemptsByStageResponse)
async def get_attempts_by_stage(
    db: Any = Depends(get_db_dep),
) -> dict[str, Any]:
    """Get attempt statistics grouped by stage.

    Returns aggregate stats (total attempts, successes, avg duration)
    for each pipeline stage from the attempts table.

    Args:
        db: Database dependency (injected).

    Returns:
        Dict with stages list containing per-stage attempt stats.

    Raises:
        HTTPException: 503 if database is not available.
    """
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        async with db._conn.execute(
            "SELECT stage, COUNT(*) as total, "
            "SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes, "
            "AVG(duration_ms) as avg_duration_ms "
            "FROM attempts GROUP BY stage"
        ) as cursor:
            rows = await cursor.fetchall()
        stages = [
            {
                "stage": str(row["stage"]),
                "total": int(row["total"]),
                "successes": int(row["successes"]),
                "avg_duration_ms": (
                    float(row["avg_duration_ms"])
                    if row["avg_duration_ms"] is not None
                    else None
                ),
            }
            for row in rows
        ]
        return {"stages": stages}
    raise HTTPException(status_code=503, detail="Database not available")


@router.get(
    "/task-completion-timeline",
    response_model=TaskCompletionTimelineResponse,
)
async def get_task_completion_timeline(
    db: Any = Depends(get_db_dep),
) -> dict[str, Any]:
    """Get task completions over time.

    Returns daily counts of completed tasks based on their updated_at
    timestamp, filtered to tasks with 'complete' or 'passing' status.

    Args:
        db: Database dependency (injected).

    Returns:
        Dict with timeline list of date/completed pairs.

    Raises:
        HTTPException: 503 if database is not available.
    """
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        async with db._conn.execute(
            "SELECT DATE(updated_at) as date, COUNT(*) as completed "
            "FROM tasks WHERE status IN ('complete', 'passing') "
            "GROUP BY DATE(updated_at) ORDER BY date"
        ) as cursor:
            rows = await cursor.fetchall()
        timeline = [
            {
                "date": str(row["date"]),
                "completed": int(row["completed"]),
            }
            for row in rows
        ]
        return {"timeline": timeline}
    raise HTTPException(status_code=503, detail="Database not available")


@router.get("/invocation-stats", response_model=InvocationStatsResponse)
async def get_invocation_stats(
    db: Any = Depends(get_db_dep),
) -> dict[str, Any]:
    """Get invocation statistics grouped by stage.

    Returns aggregate stats (count, total tokens, avg duration)
    for each pipeline stage from the invocations table.

    Args:
        db: Database dependency (injected).

    Returns:
        Dict with invocations list containing per-stage invocation stats.

    Raises:
        HTTPException: 503 if database is not available.
    """
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        async with db._conn.execute(
            "SELECT stage, COUNT(*) as count, "
            "COALESCE(SUM(token_count), 0) as total_tokens, "
            "AVG(duration_ms) as avg_duration_ms "
            "FROM invocations GROUP BY stage"
        ) as cursor:
            rows = await cursor.fetchall()
        invocations = [
            {
                "stage": str(row["stage"]),
                "count": int(row["count"]),
                "total_tokens": int(row["total_tokens"]),
                "avg_duration_ms": (
                    float(row["avg_duration_ms"])
                    if row["avg_duration_ms"] is not None
                    else None
                ),
            }
            for row in rows
        ]
        return {"invocations": invocations}
    raise HTTPException(status_code=503, detail="Database not available")
