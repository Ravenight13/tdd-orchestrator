"""Runs mixin module for database operations.

Provides functions for retrieving execution runs with optional status/limit filtering
and fetching the currently active run.
"""

from __future__ import annotations

from typing import Any

from ..singleton import get_db


async def get_execution_runs(
    execution_id: int,
    status: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Retrieve execution runs with optional status/limit filtering.

    Args:
        execution_id: The execution ID (unused - returns all runs).
        status: Optional status to filter by (e.g., "running", "passed", "failed").
        limit: Optional maximum number of runs to return.

    Returns:
        List of run record dictionaries ordered by created_at/started_at descending.
        Returns empty list if no runs match the filters.
    """
    db = await get_db()
    await db._ensure_connected()

    if not db._conn:
        return []

    # Build query with filters - NOTE: execution_id is ignored for now
    query = "SELECT * FROM execution_runs WHERE 1=1"
    params: list[Any] = []

    if status is not None:
        query += " AND status = ?"
        params.append(status)

    # Order by started_at descending
    query += " ORDER BY started_at DESC"

    if limit is not None:
        if limit <= 0:
            return []
        query += " LIMIT ?"
        params.append(limit)

    async with db._conn.execute(query, params) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_current_run(execution_id: int) -> dict[str, Any] | None:
    """Retrieve the currently active run for an execution.

    Args:
        execution_id: The execution ID (unused - returns any 'running' run).

    Returns:
        Run record dictionary with status 'running', or None if no active run exists.
    """
    db = await get_db()
    await db._ensure_connected()

    if not db._conn:
        return None

    async with db._conn.execute(
        "SELECT * FROM execution_runs WHERE status = 'running' LIMIT 1",
        ()
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None
