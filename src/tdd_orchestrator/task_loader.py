"""TDD task loader for batch initialization of orchestrator tasks.

This module provides utilities for loading TDD tasks in bulk into the
orchestrator database, with support for duplicate handling, validation,
and incremental writes for resilience.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from .database import OrchestratorDB

logger = logging.getLogger(__name__)


class LoadResult(TypedDict):
    """Result of loading TDD tasks."""

    loaded: int
    skipped: int
    errors: list[str]
    task_keys: list[str]


REQUIRED_FIELDS = {"task_key", "title"}


def _validate_task(task: dict[str, Any], index: int) -> list[str]:
    """Validate a single task dictionary.

    Args:
        task: Task dictionary to validate.
        index: Index in the task list (for error messages).

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in task or not task[field]:
            errors.append(f"Task {index}: missing required field '{field}'")

    # Validate task_key format if present
    if "task_key" in task:
        task_key = task["task_key"]
        if not isinstance(task_key, str) or not task_key.strip():
            errors.append(f"Task {index}: 'task_key' must be a non-empty string")

    # Validate depends_on is a list if present
    if "depends_on" in task and task["depends_on"] is not None:
        if not isinstance(task["depends_on"], list):
            errors.append(f"Task {index}: 'depends_on' must be a list")

    # Validate acceptance_criteria is a list if present
    if "acceptance_criteria" in task and task["acceptance_criteria"] is not None:
        if not isinstance(task["acceptance_criteria"], list):
            errors.append(f"Task {index}: 'acceptance_criteria' must be a list")

    # Validate phase and sequence are integers if present
    for field in ("phase", "sequence"):
        if field in task and task[field] is not None:
            if not isinstance(task[field], int):
                errors.append(f"Task {index}: '{field}' must be an integer")

    return errors


async def load_tdd_tasks(
    tasks: list[dict[str, Any]],
    db: OrchestratorDB | None = None,
    *,
    clear_existing: bool = False,
    skip_duplicates: bool = True,
) -> LoadResult:
    """Load TDD tasks into the orchestrator database.

    Args:
        tasks: List of task dictionaries. Each must have at minimum:
            - task_key: Unique identifier (e.g., "TDD-0A")
            - title: Human-readable title
            Optional fields:
            - goal: What this task accomplishes
            - spec_id: Reference to parent specification
            - acceptance_criteria: List of testable criteria
            - test_file: Path to test file
            - impl_file: Path to implementation file
            - depends_on: List of task_keys this depends on
            - phase: Phase number for ordering (default 0)
            - sequence: Sequence within phase (default 0)
        db: Database instance. If None, uses singleton via get_db().
        clear_existing: If True, delete all existing tasks before loading.
        skip_duplicates: If True, skip tasks where task_key already exists.
            If False, duplicate task_keys will raise an error.

    Returns:
        LoadResult with counts and details:
            - loaded: Number of tasks successfully created
            - skipped: Number of tasks skipped (duplicates or invalid)
            - errors: List of error messages
            - task_keys: List of successfully loaded task keys

    Raises:
        ValueError: If any task fails validation (missing required fields).
    """
    from .database import get_db

    if db is None:
        db = await get_db()
    assert db is not None, "get_db() must return a valid OrchestratorDB instance"

    result: LoadResult = {
        "loaded": 0,
        "skipped": 0,
        "errors": [],
        "task_keys": [],
    }

    # Validate all tasks first
    all_errors: list[str] = []
    for i, task in enumerate(tasks):
        task_errors = _validate_task(task, i)
        all_errors.extend(task_errors)

    if all_errors:
        result["errors"] = all_errors
        msg = f"Validation failed: {len(all_errors)} errors"
        raise ValueError(msg)

    # Clear existing tasks if requested
    if clear_existing:
        await _clear_all_tasks(db)
        logger.info("Cleared all existing tasks")

    # Load tasks one by one
    for task in tasks:
        task_key = task["task_key"]

        # Check for duplicates
        if skip_duplicates:
            existing = await db.get_task_by_key(task_key)
            if existing:
                result["skipped"] += 1
                logger.debug("Skipping duplicate task: %s", task_key)
                continue

        # Create the task
        try:
            await db.create_task(
                task_key=task_key,
                title=task["title"],
                goal=task.get("goal"),
                spec_id=task.get("spec_id"),
                acceptance_criteria=task.get("acceptance_criteria"),
                test_file=task.get("test_file"),
                impl_file=task.get("impl_file"),
                verify_command=task.get("verify_command"),
                done_criteria=task.get("done_criteria"),
                depends_on=task.get("depends_on"),
                phase=task.get("phase", 0),
                sequence=task.get("sequence", 0),
                module_exports=task.get("module_exports"),
            )
            result["loaded"] += 1
            result["task_keys"].append(task_key)
            logger.info("Loaded task: %s - %s", task_key, task["title"])
        except Exception as e:
            error_msg = f"Failed to create task {task_key}: {e}"
            result["errors"].append(error_msg)
            result["skipped"] += 1
            logger.error(error_msg)

    logger.info(
        "Task loading complete: %d loaded, %d skipped, %d errors",
        result["loaded"],
        result["skipped"],
        len(result["errors"]),
    )

    return result


async def _clear_all_tasks(db: OrchestratorDB, prefix: str | None = None) -> int:
    """Clear tasks from the database.

    Args:
        db: Database instance.
        prefix: If provided, only delete tasks where task_key starts with this prefix.
                If None, deletes ALL tasks (dangerous - use with caution).

    Returns:
        Number of tasks deleted.
    """
    await db._ensure_connected()
    if not db._conn:
        return 0

    # Delete attempts first (foreign key constraint)
    if prefix:
        # Delete only attempts for tasks with matching prefix
        await db._conn.execute(
            "DELETE FROM attempts WHERE task_id IN (SELECT id FROM tasks WHERE task_key LIKE ?)",
            (f"{prefix}%",),
        )
        cursor = await db._conn.execute(
            "DELETE FROM tasks WHERE task_key LIKE ?",
            (f"{prefix}%",),
        )
        deleted = cursor.rowcount
        await db._conn.commit()
        logger.info("Cleared %d tasks with prefix '%s'", deleted, prefix)
    else:
        await db._conn.execute("DELETE FROM attempts")
        cursor = await db._conn.execute("DELETE FROM tasks")
        deleted = cursor.rowcount
        await db._conn.commit()
        logger.warning("Cleared ALL %d tasks from database (no prefix filter)", deleted)

    return deleted


async def write_tasks_incremental(
    tasks: list[dict[str, Any]],
    cycle_number: int,
    db: "OrchestratorDB | None" = None,
) -> int:
    """Write tasks incrementally after a cycle completes in Pass 2.

    This function is called as a callback during decomposition to provide
    resilience - if decomposition fails mid-way, previously written tasks
    are preserved. Tasks are written without acceptance criteria (added
    in Pass 3 via update_task_acceptance_criteria).

    Args:
        tasks: List of task dictionaries from the completed cycle.
        cycle_number: The cycle number that completed.
        db: Database instance. If None, uses singleton via get_db().

    Returns:
        Number of tasks written.
    """
    from .database import get_db

    if db is None:
        db = await get_db()

    written = 0
    for task in tasks:
        task_key = task.get("task_key", "")
        if not task_key:
            logger.warning(f"Skipping task without task_key in cycle {cycle_number}")
            continue

        # Check if task already exists (idempotent writes)
        existing = await db.get_task_by_key(task_key)
        if existing:
            logger.debug(f"Task {task_key} already exists, skipping")
            continue

        try:
            await db.create_task(
                task_key=task_key,
                title=task.get("title", "Unnamed Task"),
                goal=task.get("goal"),
                spec_id=task.get("spec_id"),
                acceptance_criteria=task.get("acceptance_criteria"),  # May be empty
                test_file=task.get("test_file"),
                impl_file=task.get("impl_file"),
                verify_command=task.get("verify_command"),
                done_criteria=task.get("done_criteria"),
                depends_on=task.get("depends_on"),
                phase=task.get("phase", cycle_number),
                sequence=task.get("sequence", 0),
                module_exports=task.get("module_exports"),
            )
            written += 1
            logger.debug(f"Wrote task {task_key} from cycle {cycle_number}")
        except Exception as e:
            logger.error(f"Failed to write task {task_key}: {e}")

    logger.info(f"Cycle {cycle_number}: wrote {written} tasks incrementally")
    return written


async def update_task_acceptance_criteria(
    task_key: str,
    acceptance_criteria: list[str],
    db: "OrchestratorDB | None" = None,
) -> bool:
    """Update acceptance criteria for an existing task (Pass 3).

    This function is called after Pass 3 generates acceptance criteria
    to update tasks that were written incrementally in Pass 2.

    Args:
        task_key: The task's unique key.
        acceptance_criteria: List of acceptance criteria strings.
        db: Database instance. If None, uses singleton via get_db().

    Returns:
        True if task was updated, False if task not found.
    """
    from .database import get_db

    if db is None:
        db = await get_db()

    await db._ensure_connected()
    if not db._conn:
        return False

    async with db._write_lock:
        cursor = await db._conn.execute(
            "UPDATE tasks SET acceptance_criteria = ? WHERE task_key = ?",
            (json.dumps(acceptance_criteria), task_key),
        )
        await db._conn.commit()
        updated = cursor.rowcount > 0
        if updated:
            logger.debug(f"Updated AC for task {task_key}: {len(acceptance_criteria)} criteria")
        return updated


async def get_existing_prefixes(db: "OrchestratorDB | None" = None) -> list[str]:
    """Get unique task_key prefixes from existing tasks.

    Prefixes are determined by splitting task_key on '-' and taking the first part.
    E.g., "SF-TDD-01-01" -> "SF", "HTMX-01" -> "HTMX"

    Args:
        db: Database instance. If None, uses singleton via get_db().

    Returns:
        List of unique prefixes found in database.
    """
    if db is None:
        from .database import get_db

        db = await get_db()

    await db._ensure_connected()
    if not db._conn:
        return []

    cursor = await db._conn.execute("SELECT DISTINCT task_key FROM tasks")
    rows = await cursor.fetchall()

    prefixes: set[str] = set()
    for (task_key,) in rows:
        # Extract prefix (everything before first '-' or the whole key if no '-')
        if "-" in task_key:
            prefix = task_key.split("-")[0]
        else:
            prefix = task_key
        prefixes.add(prefix)

    return sorted(prefixes)
