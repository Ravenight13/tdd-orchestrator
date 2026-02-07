"""Composed OrchestratorDB class.

Combines all mixin classes into the final OrchestratorDB that provides
the complete database API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .connection import ConnectionMixin
from .runs import RunsMixin
from .tasks import TaskMixin
from .workers import WorkerMixin


class OrchestratorDB(ConnectionMixin, TaskMixin, WorkerMixin, RunsMixin):
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
        super().__init__(db_path)

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
