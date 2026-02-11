"""Task query, mutation, and attempt tracking operations.

Provides the TaskMixin with all task-related database methods.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


class TaskMixin:
    """Mixin providing task CRUD, status updates, and attempt tracking."""

    _conn: aiosqlite.Connection | None
    _write_lock: asyncio.Lock

    async def _ensure_connected(self) -> None: ...

    # =========================================================================
    # Task Queries
    # =========================================================================

    async def get_next_pending_task(self) -> dict[str, Any] | None:
        """Get next pending task with all dependencies met.

        Returns the highest priority task (by phase, then sequence) that is
        pending and has all dependencies either complete or passing.

        Returns:
            Task dict with all columns, or None if no tasks available.
        """
        await self._ensure_connected()
        if not self._conn:
            return None

        # Use the v_ready_tasks view for dependency resolution
        async with self._conn.execute(
            """
            SELECT * FROM v_ready_tasks
            LIMIT 1
            """
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    async def get_task_by_key(self, task_key: str) -> dict[str, Any] | None:
        """Get a task by its unique key.

        Args:
            task_key: The task identifier (e.g., "TDD-0A").

        Returns:
            Task dict with all columns, or None if not found.
        """
        await self._ensure_connected()
        if not self._conn:
            return None

        async with self._conn.execute(
            "SELECT * FROM tasks WHERE task_key = ?", (task_key,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    async def get_all_tasks(self) -> list[dict[str, Any]]:
        """Get all tasks ordered by phase and sequence.

        Returns:
            List of task dicts.
        """
        await self._ensure_connected()
        if not self._conn:
            return []

        async with self._conn.execute("SELECT * FROM tasks ORDER BY phase, sequence") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # =========================================================================
    # Task Mutations
    # =========================================================================

    async def update_task_status(self, task_key: str, status: str) -> bool:
        """Update task status.

        Args:
            task_key: The task identifier.
            status: New status (pending, in_progress, passing, complete, blocked).

        Returns:
            True if task was updated, False if task not found.

        Raises:
            ValueError: If status is invalid.
        """
        valid_statuses = {
            "pending",
            "in_progress",
            "passing",
            "complete",
            "blocked",
            "blocked-static-review",
        }
        if status not in valid_statuses:
            msg = f"Invalid status: {status}. Must be one of {valid_statuses}"
            raise ValueError(msg)

        await self._ensure_connected()
        if not self._conn:
            return False

        async with self._write_lock:
            cursor = await self._conn.execute(
                "UPDATE tasks SET status = ? WHERE task_key = ?",
                (status, task_key),
            )
            await self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                logger.info("Task %s status updated to %s", task_key, status)
            return updated

    async def mark_task_passing(self, task_key: str) -> bool:
        """Mark a task as passing all tests.

        This is a convenience method for the common transition from
        in_progress to passing.

        Args:
            task_key: The task identifier.

        Returns:
            True if task was updated, False if task not found.
        """
        return await self.update_task_status(task_key, "passing")

    async def mark_task_failing(self, task_key: str, reason: str) -> bool:
        """Mark a task as blocked/failing with a reason.

        This records the failure reason by storing an attempt record,
        then updates the task status to blocked.

        Args:
            task_key: The task identifier.
            reason: Description of why the task failed.

        Returns:
            True if task was updated, False if task not found.
        """
        await self._ensure_connected()
        if not self._conn:
            return False

        # Get task to record the attempt
        task = await self.get_task_by_key(task_key)
        if not task:
            return False

        # Record the failure in attempts table
        await self.record_attempt(
            task_id=task["id"],
            stage="green",  # Most failures happen in green phase
            success=False,
            error_message=reason,
        )

        # Update status to blocked
        return await self.update_task_status(task_key, "blocked")

    async def mark_task_complete(self, task_key: str) -> bool:
        """Mark a task as complete.

        Args:
            task_key: The task identifier.

        Returns:
            True if task was updated, False if task not found.
        """
        return await self.update_task_status(task_key, "complete")

    async def mark_task_blocked(self, task_key: str) -> bool:
        """Mark a task as blocked.

        Args:
            task_key: The task identifier.

        Returns:
            True if task was updated, False if task not found.
        """
        return await self.update_task_status(task_key, "blocked")

    # =========================================================================
    # Task Creation
    # =========================================================================

    async def create_task(
        self,
        task_key: str,
        title: str,
        *,
        goal: str | None = None,
        spec_id: int | None = None,
        acceptance_criteria: list[str] | None = None,
        test_file: str | None = None,
        impl_file: str | None = None,
        verify_command: str | None = None,
        done_criteria: str | None = None,
        depends_on: list[str] | None = None,
        phase: int = 0,
        sequence: int = 0,
        module_exports: list[str] | None = None,
        task_type: str = "implement",
    ) -> int:
        """Create a new task.

        Args:
            task_key: Unique task identifier (e.g., "TDD-0A").
            title: Human-readable task title.
            goal: What this task accomplishes.
            spec_id: Reference to parent specification.
            acceptance_criteria: List of testable criteria.
            test_file: Path to test file.
            impl_file: Path to implementation file.
            verify_command: Shell command to verify task completion.
            done_criteria: Human-readable success criteria.
            depends_on: List of task_keys this depends on.
            phase: Phase number for ordering.
            sequence: Sequence within phase.
            module_exports: PLAN9 - List of export names for this module.
            task_type: Pipeline type ("implement" or "verify-only").

        Returns:
            The new task's ID.
        """
        await self._ensure_connected()
        if not self._conn:
            return 0

        async with self._write_lock:
            cursor = await self._conn.execute(
                """
                INSERT INTO tasks (
                    task_key, title, goal, spec_id, acceptance_criteria,
                    test_file, impl_file, verify_command, done_criteria,
                    depends_on, phase, sequence, module_exports, task_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_key,
                    title,
                    goal,
                    spec_id,
                    json.dumps(acceptance_criteria) if acceptance_criteria else None,
                    test_file,
                    impl_file,
                    verify_command,
                    done_criteria,
                    json.dumps(depends_on) if depends_on else "[]",
                    phase,
                    sequence,
                    json.dumps(module_exports) if module_exports else "[]",
                    task_type,
                ),
            )
            await self._conn.commit()
            logger.info("Created task %s: %s", task_key, title)
            return cursor.lastrowid or 0

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_stats(self) -> dict[str, int]:
        """Get task status summary.

        Returns:
            Dict mapping status to count, e.g., {"pending": 5, "complete": 3}.
        """
        await self._ensure_connected()
        if not self._conn:
            return {}

        stats: dict[str, int] = {
            "pending": 0,
            "in_progress": 0,
            "passing": 0,
            "complete": 0,
            "blocked": 0,
        }

        async with self._conn.execute(
            "SELECT status, COUNT(*) as count FROM tasks GROUP BY status"
        ) as cursor:
            async for row in cursor:
                stats[row["status"]] = row["count"]

        return stats

    async def get_progress(self) -> dict[str, Any]:
        """Get detailed progress information.

        Returns:
            Dict with total, completed, percentage, and by-phase breakdown.
        """
        await self._ensure_connected()
        if not self._conn:
            return {"total": 0, "completed": 0, "percentage": 0, "by_status": {}}

        stats = await self.get_stats()
        total = sum(stats.values())
        completed = stats.get("complete", 0) + stats.get("passing", 0)

        return {
            "total": total,
            "completed": completed,
            "percentage": (completed / total * 100) if total > 0 else 0,
            "by_status": stats,
        }

    # =========================================================================
    # Attempts (for audit trail)
    # =========================================================================

    async def record_stage_attempt(
        self,
        task_id: int,
        stage: str,
        attempt_number: int,
        success: bool,
        error_message: str | None = None,
        pytest_exit_code: int | None = None,
        mypy_exit_code: int | None = None,
        ruff_exit_code: int | None = None,
    ) -> int:
        """Record a stage attempt result in the attempts table.

        Tracks individual stage execution attempts within the TDD pipeline,
        including tool exit codes for debugging failures.

        Args:
            task_id: ID of the task being processed.
            stage: Stage name (red, green, verify, fix, re_verify).
            attempt_number: Which attempt this is (1-based).
            success: Whether the stage succeeded.
            error_message: Error details if failed.
            pytest_exit_code: Exit code from pytest (0 = pass).
            mypy_exit_code: Exit code from mypy (0 = pass).
            ruff_exit_code: Exit code from ruff (0 = pass).

        Returns:
            The ID of the inserted attempt record.
        """
        await self._ensure_connected()
        if not self._conn:
            return 0

        async with self._write_lock:
            cursor = await self._conn.execute(
                """
                INSERT INTO attempts (
                    task_id, stage, attempt_number, success,
                    error_message, pytest_exit_code, mypy_exit_code, ruff_exit_code,
                    started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    task_id,
                    stage,
                    attempt_number,
                    1 if success else 0,
                    error_message,
                    pytest_exit_code,
                    mypy_exit_code,
                    ruff_exit_code,
                ),
            )
            await self._conn.commit()
            return cursor.lastrowid or 0

    async def get_stage_attempts(self, task_id: int) -> list[dict[str, Any]]:
        """Get all stage attempts for a task.

        Args:
            task_id: ID of the task.

        Returns:
            List of attempt records as dictionaries.
        """
        await self._ensure_connected()
        if not self._conn:
            return []

        async with self._conn.execute(
            """
            SELECT id, task_id, stage, attempt_number, success,
                   error_message, pytest_exit_code, mypy_exit_code, ruff_exit_code,
                   started_at
            FROM attempts
            WHERE task_id = ?
            ORDER BY id ASC
            """,
            (task_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_successful_attempt(self, task_key: str, stage: str) -> dict[str, Any] | None:
        """Get the most recent successful attempt for a task and stage.

        Args:
            task_key: The task key (e.g., 'HTMX-TDD-03-01')
            stage: The stage name (e.g., 'red', 'green')

        Returns:
            Dict with attempt details if found, None otherwise
        """
        await self._ensure_connected()
        if not self._conn:
            return None

        async with self._conn.execute(
            """
            SELECT a.* FROM attempts a
            JOIN tasks t ON a.task_id = t.id
            WHERE t.task_key = ? AND a.stage = ? AND a.success = 1
            ORDER BY a.started_at DESC
            LIMIT 1
            """,
            (task_key, stage),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def record_attempt(
        self,
        task_id: int,
        stage: str,
        *,
        success: bool = False,
        error_message: str | None = None,
        pytest_exit_code: int | None = None,
        pytest_output: str | None = None,
        mypy_exit_code: int | None = None,
        mypy_output: str | None = None,
        ruff_exit_code: int | None = None,
        ruff_output: str | None = None,
    ) -> int:
        """Record an attempt for a task stage.

        Args:
            task_id: The task's database ID.
            stage: Stage name (red, green, review, fix, verify, commit).
            success: Whether the attempt succeeded.
            error_message: Error message if failed.
            pytest_exit_code: Exit code from pytest.
            pytest_output: Output from pytest (truncated).
            mypy_exit_code: Exit code from mypy.
            mypy_output: Output from mypy.
            ruff_exit_code: Exit code from ruff.
            ruff_output: Output from ruff.

        Returns:
            The new attempt's ID.
        """
        await self._ensure_connected()
        if not self._conn:
            return 0

        async with self._write_lock:
            # Get next attempt number for this task/stage
            async with self._conn.execute(
                """
                SELECT COALESCE(MAX(attempt_number), 0) + 1
                FROM attempts
                WHERE task_id = ? AND stage = ?
                """,
                (task_id, stage),
            ) as cursor:
                row = await cursor.fetchone()
                attempt_number = row[0] if row else 1

            cursor = await self._conn.execute(
                """
                INSERT INTO attempts (
                    task_id, stage, attempt_number, success, error_message,
                    pytest_exit_code, pytest_output,
                    mypy_exit_code, mypy_output,
                    ruff_exit_code, ruff_output,
                    completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    task_id,
                    stage,
                    attempt_number,
                    1 if success else 0,
                    error_message,
                    pytest_exit_code,
                    pytest_output,
                    mypy_exit_code,
                    mypy_output,
                    ruff_exit_code,
                    ruff_output,
                ),
            )
            await self._conn.commit()
            return cursor.lastrowid or 0

    async def update_task_test_file(self, task_id: int, test_file: str) -> bool:
        """Update the test_file path for a task.

        Used by file discovery to reconcile the actual test file location
        after the RED stage creates it at a different path than expected.

        Args:
            task_id: The task's database ID.
            test_file: New relative path to the test file.

        Returns:
            True if the task was updated, False if not found.
        """
        await self._ensure_connected()
        if not self._conn:
            return False

        async with self._write_lock:
            cursor = await self._conn.execute(
                "UPDATE tasks SET test_file = ? WHERE id = ?",
                (test_file, task_id),
            )
            await self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                logger.info("Task %d test_file updated to %s", task_id, test_file)
            return updated

    # =========================================================================
    # Sibling Test Discovery
    # =========================================================================

    async def get_sibling_test_files(
        self, impl_file: str, exclude_test_file: str
    ) -> list[str]:
        """Get test files from other tasks sharing the same impl_file.

        Used during VERIFY to detect sibling test regressions — when a GREEN
        implementation change breaks tests from a different task that targets
        the same implementation module.

        Args:
            impl_file: The implementation file path to match.
            exclude_test_file: Test file of the current task (excluded).

        Returns:
            List of sibling test file paths (may be empty).
        """
        await self._ensure_connected()
        if not self._conn:
            return []

        async with self._conn.execute(
            """
            SELECT DISTINCT test_file FROM tasks
            WHERE impl_file = ? AND test_file != ?
              AND status IN ('complete', 'passing')
              AND test_file IS NOT NULL
            """,
            (impl_file, exclude_test_file),
        ) as cursor:
            rows = await cursor.fetchall()
            return [str(row["test_file"]) for row in rows]

    # =========================================================================
    # Stale Recovery (task-related)
    # =========================================================================

    async def get_stale_tasks(self) -> list[dict[str, Any]]:
        """Get tasks with expired claims.

        Returns:
            List of stale task dicts.
        """
        await self._ensure_connected()
        if not self._conn:
            return []

        async with self._conn.execute("SELECT * FROM v_stale_tasks") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def cleanup_stale_claims(self) -> int:
        """Release all expired task claims.

        Returns:
            Number of claims released.
        """
        await self._ensure_connected()
        if not self._conn:
            return 0

        async with self._write_lock:
            cursor = await self._conn.execute(
                """
                UPDATE tasks
                SET claimed_by = NULL,
                    claimed_at = NULL,
                    claim_expires_at = NULL,
                    status = 'pending'
                WHERE claim_expires_at < datetime('now')
                  AND status = 'in_progress'
                """
            )
            count = cursor.rowcount
            await self._conn.commit()

            if count > 0:
                logger.info("Released %d stale task claims", count)

            return count
