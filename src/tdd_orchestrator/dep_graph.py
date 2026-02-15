"""Runtime dependency checker for TDD Orchestrator tasks.

Validates task dependency references in the database, detects dangling
references, builds dependency graphs, and checks whether a task's
dependencies are satisfied.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .database import OrchestratorDB

logger = logging.getLogger(__name__)

# Statuses that indicate a task is finished and can unblock dependents.
_TERMINAL_STATUSES = ("complete", "passing")


def _parse_depends_on(raw: Any) -> list[str]:
    """Parse a depends_on column value into a list of task keys.

    Handles NULL, empty string, ``"null"``, ``"[]"``, and valid JSON
    arrays.  Returns an empty list for any value that does not represent
    real dependencies.

    Args:
        raw: The raw value from the ``depends_on`` column.

    Returns:
        List of dependency task-key strings.
    """
    if raw is None:
        return []
    text = str(raw).strip()
    if not text or text in ("null", "[]"):
        return []
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


async def validate_dependencies(
    db: OrchestratorDB,
) -> list[dict[str, Any]]:
    """Detect dangling dependency references across all tasks.

    A *dangling reference* is a ``depends_on`` entry whose value does not
    match any ``task_key`` in the database.

    Args:
        db: OrchestratorDB instance with an active connection.

    Returns:
        List of dicts, each with ``task_key`` (the task that has the
        dangling ref) and ``dangling_refs`` (list of missing task keys).
        An empty list means no dangling references were found.
    """
    assert db._conn is not None, "Database connection required"

    # Fetch all task_keys for the existence check.
    async with db._conn.execute("SELECT task_key FROM tasks") as cursor:
        rows = await cursor.fetchall()

    all_keys: set[str] = {str(row[0]) for row in rows}

    # Fetch task_key + depends_on for every task.
    async with db._conn.execute(
        "SELECT task_key, depends_on FROM tasks"
    ) as cursor:
        dep_rows = await cursor.fetchall()

    issues: list[dict[str, Any]] = []
    for row in dep_rows:
        task_key = str(row[0])
        deps = _parse_depends_on(row[1])
        dangling = [d for d in deps if d not in all_keys]
        if dangling:
            issues.append({"task_key": task_key, "dangling_refs": dangling})

    return issues


async def get_dependency_graph(
    db: OrchestratorDB,
) -> dict[str, list[str]]:
    """Build an adjacency list of task dependencies.

    Each key in the returned dict is a ``task_key``; its value is the
    list of task keys it depends on (edges point *from* dependent *to*
    dependency).

    Args:
        db: OrchestratorDB instance with an active connection.

    Returns:
        Adjacency-list mapping ``task_key -> [dependency_keys]``.
    """
    assert db._conn is not None, "Database connection required"

    async with db._conn.execute(
        "SELECT task_key, depends_on FROM tasks"
    ) as cursor:
        rows = await cursor.fetchall()

    graph: dict[str, list[str]] = {}
    for row in rows:
        task_key = str(row[0])
        deps = _parse_depends_on(row[1])
        graph[task_key] = deps

    return graph


async def are_dependencies_met(
    db: OrchestratorDB,
    task_key: str,
) -> bool:
    """Check whether all dependencies for *task_key* are in a terminal status.

    Terminal statuses are ``"complete"`` and ``"passing"``.

    Args:
        db: OrchestratorDB instance with an active connection.
        task_key: The task whose dependencies should be checked.

    Returns:
        ``True`` if every dependency is in a terminal status (or if the
        task has no dependencies).  ``False`` otherwise.
    """
    assert db._conn is not None, "Database connection required"

    # Fetch depends_on for the target task.
    async with db._conn.execute(
        "SELECT depends_on FROM tasks WHERE task_key = ?", (task_key,)
    ) as cursor:
        row = await cursor.fetchone()

    if row is None:
        # Task not found — treat as met (caller should verify existence).
        return True

    deps = _parse_depends_on(row[0])
    if not deps:
        return True

    # Check each dependency's status.
    for dep_key in deps:
        async with db._conn.execute(
            "SELECT status FROM tasks WHERE task_key = ?", (dep_key,)
        ) as cursor:
            dep_row = await cursor.fetchone()

        if dep_row is None:
            # Dependency doesn't exist — cannot be met.
            return False
        if str(dep_row[0]) not in _TERMINAL_STATUSES:
            return False

    return True
