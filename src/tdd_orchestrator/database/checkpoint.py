"""Checkpoint and resume database operations.

Provides the CheckpointMixin with methods for tracking pipeline stage
progress, run-task associations, and pipeline-level checkpoints.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


class CheckpointMixin:
    """Mixin providing checkpoint & resume database operations."""

    _conn: aiosqlite.Connection | None
    _write_lock: asyncio.Lock

    async def _ensure_connected(self) -> None: ...

    # =========================================================================
    # Stage Resume Queries
    # =========================================================================

    async def get_last_completed_stage(self, task_id: int) -> str | None:
        """Get the most recent successfully completed stage for a task.

        Queries the attempts table for the latest successful attempt,
        ordered by started_at descending.

        Args:
            task_id: The task database ID (integer PK).

        Returns:
            Stage name (e.g., "red", "green", "verify") or None if no
            successful attempts exist.
        """
        await self._ensure_connected()
        if not self._conn:
            return None

        async with self._conn.execute(
            """
            SELECT stage FROM attempts
            WHERE task_id = ? AND success = 1
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (task_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return str(row["stage"]) if row else None

    async def get_resumable_tasks(self) -> list[dict[str, Any]]:
        """Get tasks that have prior stage progress and can be resumed.

        Finds tasks with status 'pending' or 'in_progress' that have at
        least one successful attempt recorded.

        Returns:
            List of task dicts with their last completed stage.
        """
        await self._ensure_connected()
        if not self._conn:
            return []

        async with self._conn.execute(
            """
            SELECT t.id, t.task_key, t.status, a.stage AS last_stage
            FROM tasks t
            JOIN attempts a ON a.task_id = t.id AND a.success = 1
            WHERE t.status IN ('pending', 'in_progress')
            AND a.started_at = (
                SELECT MAX(a2.started_at) FROM attempts a2
                WHERE a2.task_id = t.id AND a2.success = 1
            )
            ORDER BY t.phase, t.sequence
            """,
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # =========================================================================
    # Run-Task Association
    # =========================================================================

    async def associate_task_with_run(
        self,
        run_id: int,
        task_id: int,
        resume_from_stage: str | None = None,
    ) -> int:
        """Associate a task with an execution run.

        Creates a run_tasks record linking the task to the run.

        Args:
            run_id: Execution run ID.
            task_id: Task ID.
            resume_from_stage: Stage name if resuming, None if fresh.

        Returns:
            The inserted row ID.
        """
        await self._ensure_connected()
        if not self._conn:
            return 0

        async with self._write_lock:
            cursor = await self._conn.execute(
                """
                INSERT OR IGNORE INTO run_tasks (run_id, task_id, resume_from_stage)
                VALUES (?, ?, ?)
                """,
                (run_id, task_id, resume_from_stage),
            )
            await self._conn.commit()
            return cursor.lastrowid or 0

    async def complete_run_task(
        self, run_id: int, task_id: int, final_status: str
    ) -> None:
        """Mark a run-task association as completed.

        Args:
            run_id: Execution run ID.
            task_id: Task ID.
            final_status: One of 'completed', 'failed', 'skipped'.
        """
        await self._ensure_connected()
        if not self._conn:
            return

        async with self._write_lock:
            await self._conn.execute(
                """
                UPDATE run_tasks
                SET completed_at = CURRENT_TIMESTAMP, final_status = ?
                WHERE run_id = ? AND task_id = ?
                """,
                (final_status, run_id, task_id),
            )
            await self._conn.commit()

    # =========================================================================
    # Pipeline Checkpoints
    # =========================================================================

    async def save_pipeline_checkpoint(
        self, run_id: int, pipeline_state: dict[str, Any]
    ) -> None:
        """Save a pipeline checkpoint to the execution run.

        Serializes the state dict to JSON and stores it in the
        pipeline_state column of execution_runs.

        Args:
            run_id: Execution run ID.
            pipeline_state: Checkpoint data to serialize.
        """
        await self._ensure_connected()
        if not self._conn:
            return

        state_json = json.dumps(pipeline_state)
        async with self._write_lock:
            await self._conn.execute(
                """
                UPDATE execution_runs
                SET pipeline_state = ?
                WHERE id = ?
                """,
                (state_json, run_id),
            )
            await self._conn.commit()

    async def load_pipeline_checkpoint(
        self, run_id: int
    ) -> dict[str, Any] | None:
        """Load a pipeline checkpoint from an execution run.

        Args:
            run_id: Execution run ID.

        Returns:
            Deserialized checkpoint dict, or None if no checkpoint exists.
        """
        await self._ensure_connected()
        if not self._conn:
            return None

        async with self._conn.execute(
            "SELECT pipeline_state FROM execution_runs WHERE id = ?",
            (run_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row and row["pipeline_state"]:
                loaded: dict[str, Any] = json.loads(str(row["pipeline_state"]))
                return loaded
            return None

    async def find_resumable_run(self, pipeline_type: str) -> int | None:
        """Find the most recent incomplete run of the given type.

        An incomplete run has status 'running' or 'failed' (not
        'completed', 'cancelled', or 'passed').

        Args:
            pipeline_type: Either 'run' or 'run-prd'.

        Returns:
            Run ID of the most recent incomplete run, or None.
        """
        await self._ensure_connected()
        if not self._conn:
            return None

        async with self._conn.execute(
            """
            SELECT id FROM execution_runs
            WHERE pipeline_type = ?
              AND status IN ('running', 'failed')
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (pipeline_type,),
        ) as cursor:
            row = await cursor.fetchone()
            return int(row["id"]) if row else None
