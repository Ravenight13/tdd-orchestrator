"""Execution runs, invocations, configuration, and metrics operations.

Provides the RunsMixin with execution tracking, config management,
git stash logging, and static review metrics.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiosqlite

from .connection import CONFIG_BOUNDS

logger = logging.getLogger(__name__)


class RunsMixin:
    """Mixin providing execution runs, config, invocations, and metrics."""

    _conn: aiosqlite.Connection | None
    _write_lock: asyncio.Lock

    async def _ensure_connected(self) -> None: ...

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
                return str(row["value"])
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
