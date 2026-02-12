"""Metrics router for Prometheus exposition format and JSON metrics."""

import json
from typing import Any

from fastapi import APIRouter, Depends, Response

from tdd_orchestrator.api.dependencies import get_db_dep
from tdd_orchestrator.metrics import get_metrics_collector

router = APIRouter()

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


@router.get("")
def metrics_endpoint() -> Response:
    """Return metrics in Prometheus exposition format.

    Returns:
        A Response with Prometheus-formatted text and appropriate content-type.
        Returns HTTP 500 with JSON error if metrics collection fails.
    """
    try:
        collector = get_metrics_collector()
        prometheus_text = collector.export_prometheus()

        return Response(
            content=prometheus_text,
            media_type=PROMETHEUS_CONTENT_TYPE,
        )
    except Exception as e:
        # Return 500 with JSON error
        error_response: dict[str, Any] = {
            "detail": f"Metrics collection failed: {str(e)}"
        }
        return Response(
            content=json.dumps(error_response),
            status_code=500,
            media_type="application/json",
        )


@router.get("/json")
async def metrics_json_endpoint(db: Any = Depends(get_db_dep)) -> dict[str, Any]:
    """Return task metrics in JSON format.

    Queries the tasks table for status counts and the attempts table
    for average duration statistics.

    Returns:
        A dictionary with pending_count, running_count, passed_count,
        failed_count, total_count, and avg_duration_seconds.
    """
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        counts: dict[str, int] = {"pending": 0, "running": 0, "passed": 0, "failed": 0}
        async with db._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status"
        ) as cursor:
            async for row in cursor:
                status = str(row["status"])
                count = int(row["cnt"])
                if status == "pending":
                    counts["pending"] += count
                elif status == "in_progress":
                    counts["running"] += count
                elif status in ("passing", "complete"):
                    counts["passed"] += count
                elif status in ("blocked", "blocked-static-review"):
                    counts["failed"] += count
        total = sum(counts.values())

        avg_duration: float | None = None
        async with db._conn.execute(
            "SELECT AVG(duration_ms) / 1000.0 as avg_sec "
            "FROM attempts WHERE success = 1 AND duration_ms IS NOT NULL"
        ) as cursor:
            row = await cursor.fetchone()
            if row and row["avg_sec"] is not None:
                avg_duration = float(row["avg_sec"])

        return {
            "pending_count": counts["pending"],
            "running_count": counts["running"],
            "passed_count": counts["passed"],
            "failed_count": counts["failed"],
            "total_count": total,
            "avg_duration_seconds": avg_duration,
        }
    return {
        "pending_count": 0,
        "running_count": 0,
        "passed_count": 0,
        "failed_count": 0,
        "total_count": 0,
        "avg_duration_seconds": None,
    }
