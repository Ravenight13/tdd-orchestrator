"""Async SQLite database for orchestrator state management.

This module provides the persistence layer for the TDD task state machine.
All operations are async using aiosqlite for non-blocking I/O.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiosqlite

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Path to schema file relative to this module
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Configuration bounds for numeric values
CONFIG_BOUNDS: dict[str, tuple[int, int]] = {
    "max_green_attempts": (1, 10),
    "green_retry_delay_ms": (0, 10000),
    "max_green_retry_time_seconds": (60, 7200),  # 1 min to 2 hours
}

# Default database path
DEFAULT_DB_PATH = Path(__file__).parent / "orchestrator.db"


class OrchestratorDB:
    """Async SQLite database for TDD task orchestration.

    This class manages all database operations for the orchestrator,
    including task state transitions, attempt tracking, and statistics.

    Usage:
        async with OrchestratorDB("tasks.db") as db:
            task = await db.get_next_pending_task()
            if task:
                await db.update_task_status(task["task_key"], "in_progress")
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file. Use ":memory:" for testing.
                     Defaults to orchestrator.db in this module's directory.
        """
        if db_path is None:
            self.db_path = DEFAULT_DB_PATH
        elif isinstance(db_path, str):
            self.db_path = Path(db_path) if db_path != ":memory:" else db_path  # type: ignore[assignment]
        else:
            self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._initialized = False
        self._write_lock = asyncio.Lock()

    async def __aenter__(self) -> OrchestratorDB:
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    async def connect(self) -> None:
        """Open database connection and initialize schema."""
        db_path = str(self.db_path) if isinstance(self.db_path, Path) else self.db_path
        # Resolve to absolute path if it's a file path
        if db_path != ":memory:":
            resolved_path = Path(db_path).resolve()
            db_exists = resolved_path.exists()
            logger.info("Database: %s (exists: %s)", resolved_path, db_exists)
        self._conn = await aiosqlite.connect(db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._initialize_schema()

    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def _ensure_connected(self) -> None:
        """Ensure database is connected."""
        if self._conn is None:
            await self.connect()

    async def _initialize_schema(self) -> None:
        """Initialize database schema from SQL file.

        Raises:
            RuntimeError: If schema initialization fails due to migration issues.
                          Delete the database file to start fresh.
        """
        if not self._conn:
            msg = "Database not connected"
            raise RuntimeError(msg)

        if self._initialized:
            return

        # Check if tasks table exists and has expected columns
        # If schema mismatch, provide clear error before executescript hangs
        try:
            async with self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    # Table exists - verify it has expected columns
                    async with self._conn.execute("PRAGMA table_info(tasks)") as pragma_cursor:
                        columns = {col[1] for col in await pragma_cursor.fetchall()}
                        required_columns = {
                            "claimed_by",
                            "claimed_at",
                            "claim_expires_at",
                            "version",
                        }
                        missing = required_columns - columns
                        if missing:
                            msg = (
                                f"Database schema is outdated (missing columns: {missing}).\n"
                                f"To fix: Delete {self.db_path} and run again."
                            )
                            raise RuntimeError(msg)
        except RuntimeError:
            raise
        except Exception as e:
            logger.debug("Schema check failed, continuing with initialization: %s", e)

        schema_sql = SCHEMA_PATH.read_text()
        async with self._write_lock:
            try:
                await self._conn.executescript(schema_sql)
                await self._conn.commit()
                self._initialized = True
                logger.info("Database schema initialized")
            except Exception as e:
                msg = (
                    f"Schema initialization failed: {e}\n"
                    f"This usually means the database schema is outdated.\n"
                    f"To fix: Delete {self.db_path} and run again."
                )
                raise RuntimeError(msg) from e

        # PLAN9: Check for module_exports column migration
        await self._migrate_module_exports()

    async def _migrate_module_exports(self) -> None:
        """Migrate database to add PLAN9 module_exports column if missing.

        This method handles schema migration for existing databases that
        don't have the module_exports column. It's idempotent and safe
        to run multiple times.
        """
        if not self._conn:
            return

        try:
            # Check if column exists by attempting a query
            await self._conn.execute("SELECT module_exports FROM tasks LIMIT 1")
            logger.debug("PLAN9: module_exports column already exists")
        except Exception:
            # Column doesn't exist, add it
            logger.info("PLAN9: Adding module_exports column to tasks table")
            async with self._write_lock:
                await self._conn.execute(
                    "ALTER TABLE tasks ADD COLUMN module_exports TEXT DEFAULT '[]'"
                )
                await self._conn.commit()
                logger.info("PLAN9: module_exports column added successfully")

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
                    depends_on, phase, sequence, module_exports
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    # =========================================================================
    # Configuration
    # =========================================================================

    async def get_config(self, key: str, default: str | None = None) -> str | None:
        """Get a configuration value.

        Args:
            key: Configuration key.
            default: Default value if key not found.

        Returns:
            Configuration value or default.
        """
        await self._ensure_connected()
        if not self._conn:
            return default

        async with self._conn.execute("SELECT value FROM config WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row["value"]
        return default

    async def get_config_int(self, key: str, default: int) -> int:
        """Get config value as int with bounds validation.

        If key is in CONFIG_BOUNDS, value is clamped to valid range.
        Logs warning if clamping occurs.

        Args:
            key: Configuration key.
            default: Default value if key not found or invalid.

        Returns:
            Configuration value as int, clamped to bounds if applicable.
        """
        raw = await self.get_config(key, str(default))
        try:
            value = int(raw) if raw else default
        except ValueError:
            logger.warning("Config %s has invalid value %r, using default %d", key, raw, default)
            return default

        if key in CONFIG_BOUNDS:
            min_val, max_val = CONFIG_BOUNDS[key]
            if value < min_val or value > max_val:
                clamped = max(min_val, min(value, max_val))
                logger.warning(
                    "Config %s=%d out of bounds (%d-%d), clamped to %d",
                    key,
                    value,
                    min_val,
                    max_val,
                    clamped,
                )
                return clamped

        return value

    async def set_config(self, key: str, value: str) -> None:
        """Set a configuration value.

        Args:
            key: Configuration key.
            value: Configuration value.
        """
        await self._ensure_connected()
        if not self._conn:
            return

        async with self._write_lock:
            await self._conn.execute(
                """
                INSERT INTO config (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, value),
            )
            await self._conn.commit()

    # =========================================================================
    # Worker Management
    # =========================================================================

    async def register_worker(self, worker_id: int) -> int:
        """Register a new worker in the pool.

        Args:
            worker_id: Unique worker identifier.

        Returns:
            Database ID of the worker record.
        """
        await self._ensure_connected()
        if not self._conn:
            return 0

        async with self._write_lock:
            cursor = await self._conn.execute(
                """
                INSERT INTO workers (worker_id, status, last_heartbeat)
                VALUES (?, 'active', CURRENT_TIMESTAMP)
                ON CONFLICT(worker_id) DO UPDATE SET
                    status = 'active',
                    last_heartbeat = CURRENT_TIMESTAMP
                RETURNING id
                """,
                (worker_id,),
            )
            row = await cursor.fetchone()
            await self._conn.commit()
            logger.info("Registered worker %d", worker_id)
            return row[0] if row else 0

    async def unregister_worker(self, worker_id: int) -> bool:
        """Mark worker as idle.

        Args:
            worker_id: Worker identifier.

        Returns:
            True if worker was updated.
        """
        await self._ensure_connected()
        if not self._conn:
            return False

        async with self._write_lock:
            cursor = await self._conn.execute(
                """
                UPDATE workers
                SET status = 'idle', current_task_id = NULL, branch_name = NULL
                WHERE worker_id = ?
                """,
                (worker_id,),
            )
            await self._conn.commit()
            return cursor.rowcount > 0

    async def update_worker_heartbeat(
        self,
        worker_id: int,
        task_id: int | None = None,
    ) -> None:
        """Update worker heartbeat timestamp.

        Args:
            worker_id: Worker identifier.
            task_id: Current task being processed (if any).
        """
        await self._ensure_connected()
        if not self._conn:
            return

        async with self._write_lock:
            # Update workers table
            await self._conn.execute(
                """
                UPDATE workers
                SET last_heartbeat = CURRENT_TIMESTAMP, current_task_id = ?
                WHERE worker_id = ?
                """,
                (task_id, worker_id),
            )

            # Append to heartbeat log
            await self._conn.execute(
                """
                INSERT INTO worker_heartbeats (worker_id, status, task_id)
                SELECT id, status, ?
                FROM workers WHERE worker_id = ?
                """,
                (task_id, worker_id),
            )

            await self._conn.commit()

    # =========================================================================
    # Task Claiming (Atomic Operations)
    # =========================================================================

    async def claim_task(
        self,
        task_id: int,
        worker_id: int,
        timeout_seconds: int = 300,
    ) -> bool:
        """Atomically claim a task for a worker.

        Uses optimistic locking to prevent race conditions.

        Args:
            task_id: Task to claim.
            worker_id: Worker claiming the task.
            timeout_seconds: Claim expiration timeout.

        Returns:
            True if task claimed successfully, False if already claimed.
        """
        await self._ensure_connected()
        if not self._conn:
            return False

        async with self._write_lock:
            try:
                # Attempt atomic claim with version check
                cursor = await self._conn.execute(
                    f"""
                    UPDATE tasks
                    SET claimed_by = ?,
                        claimed_at = CURRENT_TIMESTAMP,
                        claim_expires_at = datetime('now', '+{timeout_seconds} seconds'),
                        version = version + 1,
                        status = 'in_progress'
                    WHERE id = ?
                      AND status = 'pending'
                      AND (claimed_by IS NULL OR claim_expires_at < datetime('now'))
                    """,
                    (worker_id, task_id),
                )

                if cursor.rowcount == 0:
                    return False

                # Get worker db ID
                async with self._conn.execute(
                    "SELECT id FROM workers WHERE worker_id = ?", (worker_id,)
                ) as wcursor:
                    wrow = await wcursor.fetchone()
                    worker_db_id = wrow[0] if wrow else worker_id

                # Log claim in audit table
                await self._conn.execute(
                    """
                    INSERT INTO task_claims (task_id, worker_id)
                    VALUES (?, ?)
                    """,
                    (task_id, worker_db_id),
                )

                await self._conn.commit()
                logger.info("Worker %d claimed task %d", worker_id, task_id)
                return True

            except Exception as e:
                await self._conn.rollback()
                logger.error("Failed to claim task %d: %s", task_id, e)
                return False

    async def release_task(
        self,
        task_id: int,
        worker_id: int,
        outcome: str,
    ) -> bool:
        """Release a task claim and record outcome.

        Args:
            task_id: Task to release.
            worker_id: Worker releasing the task.
            outcome: Outcome of the task (completed, failed, timeout, released).

        Returns:
            True if task was released.
        """
        await self._ensure_connected()
        if not self._conn:
            return False

        async with self._write_lock:
            # Clear claim from tasks table
            cursor = await self._conn.execute(
                """
                UPDATE tasks
                SET claimed_by = NULL,
                    claimed_at = NULL,
                    claim_expires_at = NULL
                WHERE id = ? AND claimed_by = ?
                """,
                (task_id, worker_id),
            )

            # Get worker db ID
            async with self._conn.execute(
                "SELECT id FROM workers WHERE worker_id = ?", (worker_id,)
            ) as wcursor:
                wrow = await wcursor.fetchone()
                worker_db_id = wrow[0] if wrow else worker_id

            # Update claim audit log
            await self._conn.execute(
                """
                UPDATE task_claims
                SET released_at = CURRENT_TIMESTAMP, outcome = ?
                WHERE task_id = ? AND worker_id = ? AND released_at IS NULL
                """,
                (outcome, task_id, worker_db_id),
            )

            await self._conn.commit()
            return cursor.rowcount > 0

    async def get_claimable_tasks(self, phase: int | None = None) -> list[dict[str, Any]]:
        """Get tasks available for claiming.

        Args:
            phase: Optional phase filter.

        Returns:
            List of claimable task dicts.
        """
        await self._ensure_connected()
        if not self._conn:
            return []

        if phase is not None:
            async with self._conn.execute(
                "SELECT * FROM v_claimable_tasks WHERE phase = ? ORDER BY sequence",
                (phase,),
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with self._conn.execute(
                "SELECT * FROM v_claimable_tasks ORDER BY phase, sequence"
            ) as cursor:
                rows = await cursor.fetchall()

        return [dict(row) for row in rows]

    # =========================================================================
    # Execution Runs & Invocation Tracking
    # =========================================================================

    async def start_execution_run(self, max_workers: int) -> int:
        """Start a new execution run.

        Args:
            max_workers: Maximum workers configured for this run.

        Returns:
            Run ID.
        """
        await self._ensure_connected()
        if not self._conn:
            return 0

        async with self._write_lock:
            cursor = await self._conn.execute(
                """
                INSERT INTO execution_runs (max_workers, status)
                VALUES (?, 'running')
                """,
                (max_workers,),
            )
            await self._conn.commit()
            return cursor.lastrowid or 0

    async def complete_execution_run(self, run_id: int, status: str = "completed") -> None:
        """Mark execution run as complete.

        Args:
            run_id: Run to complete.
            status: Final status (completed, failed, cancelled).
        """
        await self._ensure_connected()
        if not self._conn:
            return

        async with self._write_lock:
            await self._conn.execute(
                """
                UPDATE execution_runs
                SET completed_at = CURRENT_TIMESTAMP, status = ?
                WHERE id = ?
                """,
                (status, run_id),
            )
            await self._conn.commit()

    async def record_invocation(
        self,
        run_id: int,
        stage: str,
        worker_id: int | None = None,
        task_id: int | None = None,
        token_count: int | None = None,
        duration_ms: int | None = None,
    ) -> int:
        """Record an API invocation.

        Args:
            run_id: Current execution run ID.
            stage: Stage name (red, green, review, etc).
            worker_id: Worker that made the invocation.
            task_id: Task associated with invocation.
            token_count: Tokens used (if available).
            duration_ms: Duration in milliseconds.

        Returns:
            Invocation ID.
        """
        await self._ensure_connected()
        if not self._conn:
            return 0

        async with self._write_lock:
            cursor = await self._conn.execute(
                """
                INSERT INTO invocations (run_id, worker_id, task_id, stage, token_count, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, worker_id, task_id, stage, token_count, duration_ms),
            )

            # Update run total
            await self._conn.execute(
                """
                UPDATE execution_runs
                SET total_invocations = total_invocations + 1
                WHERE id = ?
                """,
                (run_id,),
            )

            await self._conn.commit()
            return cursor.lastrowid or 0

    async def get_invocation_count(self, run_id: int) -> int:
        """Get total invocations for a run.

        Args:
            run_id: Execution run ID.

        Returns:
            Number of invocations.
        """
        await self._ensure_connected()
        if not self._conn:
            return 0

        async with self._conn.execute(
            "SELECT total_invocations FROM execution_runs WHERE id = ?",
            (run_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def check_invocation_budget(self, run_id: int) -> tuple[int, int, bool]:
        """Check invocation budget status.

        Args:
            run_id: Execution run ID.

        Returns:
            Tuple of (current_count, limit, is_warning).
            is_warning is True if at 80% of limit.
        """
        count = await self.get_invocation_count(run_id)
        limit = int(await self.get_config("max_invocations_per_session", "100") or "100")
        threshold = int(await self.get_config("budget_warning_threshold", "80") or "80")

        is_warning = count >= (limit * threshold // 100)
        return count, limit, is_warning

    # =========================================================================
    # Git Stash Audit Logging
    # =========================================================================

    async def log_stash_operation(
        self,
        task_id: int,
        stash_id: str | None,
        operation: str,
        success: bool,
        error_message: str | None = None,
    ) -> int:
        """Log a git stash operation to the audit table.

        Records stash operations for audit trail and debugging.

        Args:
            task_id: ID of the task being processed.
            stash_id: Git stash identifier (e.g., 'stash@{0}').
            operation: Operation type ('create', 'drop', 'pop', 'skip').
            success: Whether the operation succeeded.
            error_message: Error details if failed.

        Returns:
            The ID of the inserted log record.
        """
        await self._ensure_connected()
        if not self._conn:
            return 0

        async with self._write_lock:
            cursor = await self._conn.execute(
                """
                INSERT INTO git_stash_log (task_id, stash_id, operation, success, error_message)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, stash_id, operation, 1 if success else 0, error_message),
            )
            await self._conn.commit()
            return cursor.lastrowid or 0

    # =========================================================================
    # Stale Recovery
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

    async def get_stale_workers(self) -> list[dict[str, Any]]:
        """Get workers with stale heartbeats (10+ minutes).

        Returns:
            List of stale worker dicts.
        """
        await self._ensure_connected()
        if not self._conn:
            return []

        async with self._conn.execute("SELECT * FROM v_stale_workers") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # =========================================================================
    # Static Review Metrics (PLAN12 Phase 1B Shadow Mode)
    # =========================================================================

    async def log_static_review_metric(
        self,
        task_id: int,
        task_key: str,
        check_name: str,
        severity: str,
        line_number: int,
        message: str,
        code_snippet: str | None = None,
        fix_guidance: str | None = None,
        run_id: int | None = None,
    ) -> int:
        """Log a static review metric for shadow mode tracking.

        Args:
            task_id: ID of the task being checked.
            task_key: Task key (e.g., "TDD-01").
            check_name: Name of the check/pattern (e.g., "lambda_iteration").
            severity: Either "error" or "warning".
            line_number: Line number where violation occurred.
            message: Human-readable description of the violation.
            code_snippet: The offending line of code (optional).
            fix_guidance: Suggested fix (optional).
            run_id: Current execution run ID (optional).

        Returns:
            The ID of the inserted record, or 0 on failure.
        """
        await self._ensure_connected()
        if not self._conn:
            return 0

        async with self._write_lock:
            cursor = await self._conn.execute(
                """
                INSERT INTO static_review_metrics (
                    task_id, task_key, run_id, check_name, severity,
                    line_number, message, code_snippet, fix_guidance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    task_key,
                    run_id,
                    check_name,
                    severity,
                    line_number,
                    message,
                    code_snippet,
                    fix_guidance,
                ),
            )
            await self._conn.commit()
            return cursor.lastrowid or 0

    async def get_shadow_mode_stats(self) -> list[dict[str, Any]]:
        """Get shadow mode metrics summary for promotion decisions.

        Returns:
            List of dicts with check_name, total_warnings, reviewed_count,
            false_positive_count, true_positive_count, fp_rate_percent,
            first_detected, last_detected.
        """
        await self._ensure_connected()
        if not self._conn:
            return []

        async with self._conn.execute("SELECT * FROM v_shadow_mode_summary") as cursor:
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

    # =========================================================================
    # Generic Query/Update Helpers (for testing)
    # =========================================================================

    async def execute_query(
        self,
        query: str,
        params: tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a SELECT query and return results as list of dicts.

        Args:
            query: SQL SELECT query.
            params: Optional query parameters.

        Returns:
            List of result rows as dictionaries.
        """
        await self._ensure_connected()
        if not self._conn:
            return []

        async with self._conn.execute(query, params or ()) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def execute_update(
        self,
        query: str,
        params: tuple[Any, ...] | None = None,
    ) -> int:
        """Execute an INSERT/UPDATE/DELETE query and return affected rows.

        Args:
            query: SQL INSERT/UPDATE/DELETE query.
            params: Optional query parameters.

        Returns:
            Number of rows affected.
        """
        await self._ensure_connected()
        if not self._conn:
            return 0

        async with self._write_lock:
            cursor = await self._conn.execute(query, params or ())
            await self._conn.commit()
            return cursor.rowcount


# Singleton instance for MCP tools
_db_instance: OrchestratorDB | None = None

# Custom path for database (allows configuration before first get_db call)
_custom_db_path: str | Path | None = None


def set_db_path(path: str | Path) -> None:
    """Set custom database path before first get_db() call.

    This allows configuring where the database is created before
    the singleton is initialized. Useful for testing.

    Args:
        path: Path to SQLite database file.

    Raises:
        RuntimeError: If database is already initialized.
    """
    global _custom_db_path, _db_instance
    if _db_instance is not None:
        msg = "Cannot set db_path after database is initialized. Call reset_db() first."
        raise RuntimeError(msg)
    _custom_db_path = path
    logger.info("Database path set to: %s", path)


async def get_db() -> OrchestratorDB:
    """Get the singleton database instance.

    Returns:
        The singleton OrchestratorDB instance, connected and ready.
    """
    global _db_instance, _custom_db_path
    if _db_instance is None:
        _db_instance = OrchestratorDB(_custom_db_path)
        await _db_instance.connect()
    return _db_instance


async def reset_db() -> None:
    """Reset the singleton database instance.

    Useful for testing to ensure a fresh database.
    Also clears any custom db_path setting.
    """
    global _db_instance, _custom_db_path
    if _db_instance is not None:
        await _db_instance.close()
        _db_instance = None
    _custom_db_path = None
