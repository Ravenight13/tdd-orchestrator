"""Worker statistics aggregation function.

Provides get_all_workers() function to retrieve aggregated worker statistics
from the v_worker_stats view.
"""

from __future__ import annotations

from typing import Any

from ..singleton import get_db


async def get_all_workers() -> list[dict[str, Any]]:
    """Query v_worker_stats view to return aggregated worker statistics.

    Returns:
        List of dicts containing worker statistics. Each dict contains:
        - worker_id: Worker identifier (int)
        - total_tasks: Total number of task claims (int)
        - completed_tasks: Number of completed tasks (int)
        - failed_tasks: Number of failed tasks (int)
        - current_status: Current worker status (str)

    Raises:
        Exception: If database connection is not available.
    """
    db = await get_db()

    if not db._conn:
        raise Exception("Database connection is not available")

    async with db._conn.execute(
        """
        SELECT
            worker_id,
            total_claims,
            completed_claims,
            failed_claims,
            status
        FROM v_worker_stats
        """
    ) as cursor:
        rows = await cursor.fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "worker_id": int(row[0]),
                "total_tasks": int(row[1]) if row[1] is not None else 0,
                "completed_tasks": int(row[2]) if row[2] is not None else 0,
                "failed_tasks": int(row[3]) if row[3] is not None else 0,
                "current_status": str(row[4]),
            }
        )

    return result
