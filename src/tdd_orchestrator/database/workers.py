"""Worker management and task claiming operations.

Provides the WorkerMixin with worker registration, heartbeats,
and atomic task claiming with optimistic locking.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


class WorkerMixin:
    """Mixin providing worker registration, heartbeats, and task claiming."""

    _conn: aiosqlite.Connection | None
    _write_lock: asyncio.Lock

    async def _ensure_connected(self) -> None: ...

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
    # Stale Recovery (worker-related)
    # =========================================================================

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
