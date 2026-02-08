"""Task mixin module for database operations.

Provides functions for retrieving tasks by status using parameterized SQL.
"""

from __future__ import annotations

from typing import Any

from ..singleton import get_db


def _build_filter_clause(
    status: str | None,
    phase: str | None,
    complexity: str | None,
) -> tuple[str, list[Any]]:
    """Build WHERE clause and parameters from filter values.

    Args:
        status: Filter by task status.
        phase: Filter by task phase.
        complexity: Filter by complexity level.

    Returns:
        Tuple of (where_clause_string, parameters_list).
    """
    where_clauses: list[str] = []
    params: list[Any] = []

    if status is not None:
        where_clauses.append("status = ?")
        params.append(status)

    if phase is not None:
        where_clauses.append("phase = ?")
        params.append(phase)

    if complexity is not None:
        where_clauses.append("complexity = ?")
        params.append(complexity)

    where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
    return where_clause, params


def _build_pagination_clause(limit: int | None, offset: int | None) -> str:
    """Build LIMIT/OFFSET clause for pagination.

    Args:
        limit: Maximum number of rows to return.
        offset: Number of rows to skip.

    Returns:
        SQL pagination clause string (may be empty).
    """
    # SQL requires LIMIT if OFFSET is used
    if limit is not None:
        clause = f" LIMIT {limit}"
        if offset is not None:
            clause += f" OFFSET {offset}"
        return clause
    elif offset is not None:
        # If only offset is provided, use -1 for unlimited
        return f" LIMIT -1 OFFSET {offset}"
    return ""


async def get_tasks_by_status(status: str) -> list[dict[str, Any]]:
    """Retrieve all tasks matching the given status.

    Uses parameterized SQL to prevent SQL injection attacks.

    Args:
        status: The status to filter by (e.g., "pending", "in_progress", "complete").

    Returns:
        List of task dictionaries. Each dict contains all task columns including:
        - id (or task_id): Task identifier
        - spec_id: Reference to parent specification
        - status: Current task status
        - created_at: Task creation timestamp
        - updated_at: Last update timestamp
        - result: Task result (if any)
        - agent_id: Agent handling the task (if any)
        Returns empty list if no tasks match the status.
    """
    db = await get_db()
    await db._ensure_connected()

    if not db._conn:
        return []

    # Use parameterized query to prevent SQL injection
    async with db._conn.execute(
        "SELECT * FROM tasks WHERE status = ?",
        (status,)
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_tasks_filtered(
    status: str | None = None,
    phase: str | None = None,
    complexity: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    """Retrieve tasks with flexible filtering and pagination.

    Dynamically constructs WHERE clause based on provided filters.
    Uses parameterized SQL to prevent SQL injection attacks.

    Args:
        status: Filter by task status (e.g., "pending", "in_progress", "completed").
        phase: Filter by task phase (e.g., "RED", "GREEN", "REFACTOR").
        complexity: Filter by complexity level (e.g., "low", "medium", "high").
        limit: Maximum number of tasks to return (pagination).
        offset: Number of tasks to skip (pagination).

    Returns:
        Dictionary with two keys:
        - "tasks": List of task dictionaries matching the filters
        - "total": Total count of all matching tasks (ignoring limit/offset)
    """
    db = await get_db()
    await db._ensure_connected()

    if not db._conn:
        return {"tasks": [], "total": 0}

    where_clause, params = _build_filter_clause(status, phase, complexity)

    # Get total count of matching rows
    count_query = f"SELECT COUNT(*) FROM tasks WHERE {where_clause}"
    async with db._conn.execute(count_query, params) as cursor:
        row = await cursor.fetchone()
        total = row[0] if row else 0

    # Build and execute main query with pagination
    query = f"SELECT * FROM tasks WHERE {where_clause}"
    query += _build_pagination_clause(limit, offset)

    async with db._conn.execute(query, params) as cursor:
        rows = await cursor.fetchall()
        tasks = [dict(row) for row in rows]

    return {"tasks": tasks, "total": total}
